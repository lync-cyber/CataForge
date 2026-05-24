"""Graph store abstraction and rdflib-backed default implementation.

The ``GraphStore`` ABC defines the read/write/query/validate surface that
all knowledge-graph consumers depend on. ``RDFLibStore`` is the default
backend — pure Python, BSD-licensed, zero compilation. Backends that
trade portability for speed (e.g. oxigraph) implement the same ABC and
register via the ``StoreBackendPlugin`` hook documented in
``docs/research/kg-feature-upgrade-design.md`` §2.6.

Physical layout on disk under ``<project_root>/docs/.doc-graph/`` follows
§2.2 of the same design note: ``instances.nq`` is the primary git-tracked
N-Quads file (sorted lexicographically per line so diffs stay stable),
plus a sibling ``_meta.json`` carrying schema version and backend name.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, cast

from rdflib import BNode, Dataset, Graph, Literal, URIRef
from rdflib.namespace import NamespaceManager
from rdflib.query import ResultRow
from rdflib.term import Node

from cataforge.kg.iri import IRIExpansionError
from cataforge.kg.iri import expand_curie as _shared_expand_curie
from cataforge.kg.ontology import NAMESPACES as _BUILTIN_PREFIXES

SCHEMA_VERSION = "1"
GRAPH_DIRNAME = ".doc-graph"
INSTANCES_FILENAME = "instances.nq"
META_FILENAME = "_meta.json"
INFERRED_GRAPH_IRI = "urn:cataforge:inferred"


class Triple(NamedTuple):
    """User-facing triple. Strings are CURIEs or full IRIs; literal objects
    can be int / float / bool and are coerced to typed RDF literals on add."""

    s: str
    p: str
    o: str | int | float | bool


@dataclass(frozen=True)
class ValidationReport:
    """Outcome of a SHACL validate() run.

    ``conforms`` is the single source of truth for "did validation pass";
    ``results_text`` is pyshacl's human-readable report; ``violation_count``
    is the number of ``sh:Violation`` entries in the result graph (callers
    that need finer severity buckets should re-query ``results_graph``)."""

    conforms: bool
    results_text: str
    violation_count: int


class StoreError(RuntimeError):
    """Raised for store-internal failures (load / persist / serialization)."""


def _expand_curie(token: str) -> str:
    """Store-flavoured wrapper over :func:`cataforge.kg.iri.expand_curie`.

    Translates :class:`~cataforge.kg.iri.IRIExpansionError` into the
    module-local :class:`StoreError` so callers that already catch the
    store-side exception type keep working.
    """
    try:
        return _shared_expand_curie(token)
    except IRIExpansionError as exc:
        raise StoreError(str(exc)) from exc


def _term_to_node(token: str) -> URIRef | BNode:
    """Coerce a subject / predicate token into an rdflib node."""
    if token.startswith("_:"):
        return BNode(token[2:])
    return URIRef(_expand_curie(token))


def _object_to_node(value: str | int | float | bool) -> Node:
    """Coerce a Triple.o value into an rdflib node.

    ``bool`` must be tested before ``int`` because ``isinstance(True, int)``
    is True in Python; reversing the order would type-tag every boolean as
    ``xsd:integer``."""
    if isinstance(value, bool):
        return Literal(value)
    if isinstance(value, int | float):
        return Literal(value)
    if value.startswith(("http://", "https://", "urn:", "_:")):
        return _term_to_node(value)
    if ":" in value and value.split(":", 1)[0] in _BUILTIN_PREFIXES:
        return URIRef(_expand_curie(value))
    return Literal(value)


def graph_dir_for(project_root: str | Path) -> Path:
    """Return the absolute path to ``<project_root>/docs/<GRAPH_DIRNAME>``."""
    return Path(project_root).resolve() / "docs" / GRAPH_DIRNAME


class GraphStore(ABC):
    """Backend-agnostic graph CRUD + SPARQL + validation surface.

    Implementations must honour two invariants documented in the design note:
    (1) ``persist()`` writes triples in a deterministic byte-stable order so
    git diffs stay reviewable, and (2) ``query()`` returns rows as plain
    ``dict[str, str]`` so callers don't depend on backend-specific node types."""

    backend_name: str = "abstract"

    @abstractmethod
    def load(self, project_root: str | Path) -> None: ...

    @abstractmethod
    def persist(self) -> None: ...

    @abstractmethod
    def add(
        self,
        triples: Iterable[Triple],
        named_graph: str | None = None,
    ) -> None: ...

    @abstractmethod
    def remove(self, pattern: Triple) -> int: ...

    @abstractmethod
    def query(self, sparql: str) -> list[dict[str, str]]: ...

    @abstractmethod
    def update(self, sparql_update: str) -> None: ...

    @abstractmethod
    def validate(
        self,
        shape_graph: str | Path | None = None,
    ) -> ValidationReport: ...

    @abstractmethod
    def apply_inference(self, triples: Iterable[tuple]) -> int:
        """Persist derived triples into ``INFERRED_GRAPH_IRI``; return new-triple count."""
        ...

    @abstractmethod
    def __len__(self) -> int: ...

    @abstractmethod
    def __iter__(self) -> Iterator[tuple[str, str, str, str | None]]: ...


class RDFLibStore(GraphStore):
    """Default backend — single rdflib :class:`Dataset` held in memory,
    persisted as sorted N-Quads. Suited to <5k triples; above that, swap to
    :class:`cataforge.kg.store_oxigraph.OxigraphStore` via the
    ``StoreBackendPlugin`` registration mechanism."""

    backend_name = "rdflib"

    def __init__(self) -> None:
        self._dataset: Dataset = Dataset()
        self._project_root: Path | None = None
        for prefix, iri in _BUILTIN_PREFIXES.items():
            self._dataset.bind(prefix, iri, override=True)

    def load(self, project_root: str | Path) -> None:
        """Read ``<project_root>/docs/.doc-graph/instances.nq`` into memory.

        A missing file is treated as a fresh project (initialise empty
        dataset, do not raise). A malformed file raises :class:`StoreError`."""
        root = Path(project_root).resolve()
        self._project_root = root
        instances_path = graph_dir_for(root) / INSTANCES_FILENAME
        if not instances_path.is_file():
            return
        try:
            self._dataset.parse(source=str(instances_path), format="nquads")
        except Exception as exc:
            raise StoreError(
                f"Failed to parse {instances_path}: {exc}"
            ) from exc

    def persist(self) -> None:
        """Serialise to sorted N-Quads and write ``instances.nq`` + ``_meta.json``.

        Sort key is the verbatim N-Quads line; rdflib's own per-quad
        rendering handles literal escaping and IRI angle-bracketing, so
        line-level lexicographic sort is enough for byte-stable diffs."""
        if self._project_root is None:
            raise StoreError(
                "persist() called before load(); set a project root first."
            )
        gdir = graph_dir_for(self._project_root)
        gdir.mkdir(parents=True, exist_ok=True)

        raw = self._dataset.serialize(format="nquads")
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        lines.sort()
        body = "\n".join(lines)
        if body:
            body += "\n"
        (gdir / INSTANCES_FILENAME).write_text(body, encoding="utf-8")

        meta = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds",
            ),
            "store_backend": self.backend_name,
            "triple_count": len(self),
        }
        (gdir / META_FILENAME).write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def add(
        self,
        triples: Iterable[Triple],
        named_graph: str | None = None,
    ) -> None:
        graph: Graph
        if named_graph is None:
            graph = self._dataset.default_graph
        else:
            graph = self._dataset.graph(URIRef(_expand_curie(named_graph)))
        for t in triples:
            graph.add((_term_to_node(t.s), _term_to_node(t.p), _object_to_node(t.o)))

    def remove(self, pattern: Triple) -> int:
        """Remove every quad matching the pattern across all named graphs.

        ``"*"`` in any slot is treated as a wildcard. Returns the number of
        quads actually deleted (post-removal count delta)."""
        s_node = None if pattern.s == "*" else _term_to_node(pattern.s)
        p_node = None if pattern.p == "*" else _term_to_node(pattern.p)
        o_node: Node | None
        if isinstance(pattern.o, str) and pattern.o == "*":
            o_node = None
        else:
            o_node = _object_to_node(pattern.o)
        before = len(self)
        for ctx in list(self._dataset.graphs()):
            ctx.remove((s_node, p_node, o_node))
        return before - len(self)

    def query(self, sparql: str) -> list[dict[str, str]]:
        """Execute a SPARQL SELECT (or ASK) and return rows as string dicts.

        ASK returns a single-row dict ``{"_ask": "true" | "false"}`` to keep
        the return type uniform; CONSTRUCT / DESCRIBE are unsupported here —
        callers wanting graph-shaped output should use :meth:`update` to
        materialise into a named graph, then re-query."""
        result = self._dataset.query(sparql)
        if result.type == "ASK":
            return [{"_ask": "true" if bool(result.askAnswer) else "false"}]
        rows: list[dict[str, str]] = []
        var_names = [str(v) for v in (result.vars or [])]
        for raw_row in result:
            # rdflib stubs type the iterator's element as Node | bool | tuple,
            # but in SELECT mode it is always a ResultRow that supports both
            # positional and Variable / str indexing.
            row = cast(ResultRow, raw_row)
            rows.append(
                {
                    name: ("" if row[name] is None else str(row[name]))
                    for name in var_names
                },
            )
        return rows

    def update(self, sparql_update: str) -> None:
        self._dataset.default_graph.update(sparql_update)

    def apply_inference(self, triples: Iterable[tuple]) -> int:
        """Persist derived triples into ``INFERRED_GRAPH_IRI``; return new-triple count."""
        graph = self._dataset.graph(URIRef(INFERRED_GRAPH_IRI))
        before = len(graph)
        for stmt in triples:
            graph.add(stmt)
        return len(graph) - before

    def validate(
        self,
        shape_graph: str | Path | None = None,
    ) -> ValidationReport:
        """Validate the current dataset against a SHACL shape graph.

        When ``shape_graph`` is None the SHACL constraints are expected to
        be co-resident in the dataset (i.e. callers loaded shapes into a
        named graph via :meth:`add` already)."""
        # Imported lazily so importing this module doesn't pull in pyshacl's
        # OWL / SHACL machinery for callers that only need plain CRUD.
        from pyshacl import validate as pyshacl_validate
        from rdflib.namespace import SH

        shapes_graph = None
        if shape_graph is not None:
            shapes_graph = Graph()
            shapes_graph.parse(source=str(shape_graph))

        conforms, results_graph, results_text = pyshacl_validate(
            data_graph=self._dataset,
            shacl_graph=shapes_graph,
            ont_graph=None,
            inference="none",
            advanced=True,
            meta_shacl=False,
            debug=False,
        )
        violation_count = sum(
            1
            for _ in results_graph.subjects(
                predicate=SH.resultSeverity, object=SH.Violation,
            )
        )
        return ValidationReport(
            conforms=bool(conforms),
            results_text=str(results_text),
            violation_count=violation_count,
        )

    def __len__(self) -> int:
        return sum(1 for _ in self._dataset.quads((None, None, None, None)))

    def __iter__(self) -> Iterator[tuple[str, str, str, str | None]]:
        default_id = self._dataset.default_graph.identifier
        for s, p, o, g in self._dataset.quads((None, None, None, None)):
            graph_id = None if g is None or g == default_id else str(g)
            yield (str(s), str(p), str(o), graph_id)

    def namespace_manager(self) -> NamespaceManager:
        """Expose the underlying NamespaceManager so callers can register
        additional prefixes (used by :mod:`cataforge.kg.ontology` to attach
        L3 project namespaces declared in framework.json)."""
        return self._dataset.namespace_manager
