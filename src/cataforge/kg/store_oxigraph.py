"""Sample StoreBackendPlugin wrapping `pyoxigraph` (design §E4).

Implements the same :class:`~cataforge.kg.store.GraphStore` ABC as
:class:`RDFLibStore` so callers can swap backends via the
``StoreBackendPlugin`` hook with no other changes. The Rust-backed
oxigraph store is the recommended escape hatch when the perf budget
flagged in :mod:`cataforge.kg.benchmark` blows past 5k triples (design
§2.1 / R-02).

Lazy-imports ``pyoxigraph`` so that the module loads in environments
where the extra hasn't been installed — :class:`OxigraphStore` will
raise on first use with an actionable hint. The plugin entry point
(:func:`register`) follows the protocol expected by
:func:`cataforge.kg.plugin_hooks.load_plugins`.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from cataforge.kg.ontology import NAMESPACES
from cataforge.kg.store import (
    GraphStore,
    StoreError,
    Triple,
    ValidationReport,
    _expand_curie,
)


class OxigraphStore(GraphStore):
    """Oxigraph (Rust) implementation of :class:`GraphStore`.

    The backend is a thin wrapper because oxigraph already exposes SPARQL
    1.1 SELECT / UPDATE; the only translation we do is converting
    Triple's mixed-type ``o`` field to ``NamedNode`` / ``Literal`` and
    serialising query rows back to ``dict[str, str]``."""

    backend_name = "oxigraph"

    def __init__(self) -> None:
        try:
            import pyoxigraph as _pyoxi  # type: ignore[import-not-found]  # noqa: F401
        except ImportError as exc:
            raise StoreError(
                "OxigraphStore requires the `pyoxigraph` extra. Install with "
                "`pip install cataforge[oxigraph]` or `pip install pyoxigraph`.",
            ) from exc
        Store = _pyoxi.Store  # noqa: N806 — third-party class re-bound locally
        self._oxi: Any = Store()
        self._project_root: Path | None = None

    def load(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root).resolve()
        # OxigraphStore persists via its own snapshot mechanism; this
        # backend treats ``persist()`` as authoritative and loads the
        # snapshot file only if it exists. The on-disk N-Quads form is
        # readable by the rdflib backend too so a snapshot is portable.
        import pyoxigraph as _pyoxi

        snapshot_file = self._snapshot_file()
        if snapshot_file.is_file():
            self._oxi.load(path=str(snapshot_file), format=_pyoxi.RdfFormat.N_QUADS)

    def persist(self) -> None:
        if self._project_root is None:
            raise StoreError("persist() called before load()")
        import pyoxigraph as _pyoxi

        snapshot_file = self._snapshot_file()
        snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        # In-memory pyoxigraph stores cannot ``backup`` (that's RocksDB-only).
        # Dump to N-Quads instead — atomic single-file write, portable across
        # backends, and git-trackable just like the rdflib snapshot.
        with snapshot_file.open("wb") as fh:
            self._oxi.dump(fh, _pyoxi.RdfFormat.N_QUADS)

    def _snapshot_file(self) -> Path:
        if self._project_root is None:
            raise StoreError(
                "OxigraphStore._snapshot_file() requires project_root; "
                "call load() first."
            )
        return (
            self._project_root / "docs" / ".doc-graph" / "oxigraph" / "snapshot.nq"
        )

    def add(
        self,
        triples: Iterable[Triple],
        named_graph: str | None = None,
    ) -> None:
        import pyoxigraph as _pyoxi

        Quad = _pyoxi.Quad  # noqa: N806 — third-party class re-bound locally
        graph_node = (
            _to_named_node(named_graph) if named_graph else None
        )
        for t in triples:
            self._oxi.add(
                Quad(
                    _to_named_node(t.s),
                    _to_named_node(t.p),
                    _to_object(t.o),
                    graph_node,
                ),
            )

    def remove(self, pattern: Triple) -> int:
        before = len(self)
        s = None if pattern.s == "*" else _to_named_node(pattern.s)
        p = None if pattern.p == "*" else _to_named_node(pattern.p)
        o = (
            None
            if isinstance(pattern.o, str) and pattern.o == "*"
            else _to_object(pattern.o)
        )
        for quad in list(self._oxi.quads_for_pattern(s, p, o, None)):
            self._oxi.remove(quad)
        return before - len(self)

    def query(self, sparql: str) -> list[dict[str, str]]:
        import pyoxigraph as _pyoxi

        prefix_header = "\n".join(
            f"PREFIX {pfx}: <{iri}>" for pfx, iri in NAMESPACES.items()
        )
        result = self._oxi.query(prefix_header + "\n" + sparql)
        # pyoxigraph returns ``QueryBoolean`` (ASK), ``QuerySolutions``
        # (SELECT), or ``QueryTriples`` (CONSTRUCT). We map the first two;
        # CONSTRUCT is intentionally not supported here (mirrors RDFLibStore).
        if isinstance(result, _pyoxi.QueryBoolean):
            return [{"_ask": "true" if bool(result) else "false"}]
        # ``variables`` lives on the parent ``QuerySolutions`` since 0.4;
        # capture once before iterating individual solutions. The key is the
        # bare variable name (``id``), not the SPARQL form (``?id``), so
        # rows[i]["id"] matches the rdflib backend's contract.
        variables = list(result.variables)
        rows: list[dict[str, str]] = []
        for solution in result:
            row: dict[str, str] = {}
            for var in variables:
                value = solution[var]
                row[var.value] = _term_to_str(value) if value is not None else ""
            rows.append(row)
        return rows

    def update(self, sparql_update: str) -> None:
        prefix_header = "\n".join(
            f"PREFIX {pfx}: <{iri}>" for pfx, iri in NAMESPACES.items()
        )
        self._oxi.update(prefix_header + "\n" + sparql_update)

    def validate(
        self, shape_graph: str | Path | None = None,
    ) -> ValidationReport:
        # pyoxigraph itself doesn't ship SHACL; defer to pyshacl loaded
        # against the same rdflib-shaped graph we use for the default
        # backend. This keeps validation parity across backends.
        from io import BytesIO

        import pyoxigraph as _pyoxi
        from rdflib import Graph

        buf = BytesIO()
        self._oxi.dump(buf, _pyoxi.RdfFormat.N_QUADS)
        data_graph = Graph()
        data_graph.parse(data=buf.getvalue(), format="nquads")

        from pyshacl import validate as pyshacl_validate
        from rdflib.namespace import SH

        shapes_graph = None
        if shape_graph is not None:
            shapes_graph = Graph()
            shapes_graph.parse(source=str(shape_graph))

        conforms, results_graph, results_text = pyshacl_validate(
            data_graph=data_graph,
            shacl_graph=shapes_graph,
            inference="none",
            advanced=True,
            meta_shacl=False,
            debug=False,
        )
        violation_count = sum(
            1 for _ in results_graph.subjects(
                predicate=SH.resultSeverity, object=SH.Violation,
            )
        )
        return ValidationReport(
            conforms=bool(conforms),
            results_text=str(results_text),
            violation_count=violation_count,
        )

    def __len__(self) -> int:
        return sum(1 for _ in self._oxi)

    def __iter__(self) -> Iterator[tuple[str, str, str, str | None]]:
        for quad in self._oxi:
            obj = quad.object
            obj_str = str(obj.value) if hasattr(obj, "value") else str(obj)
            g = quad.graph_name
            graph_str = (
                str(g.value)
                if g is not None and hasattr(g, "value")
                else None
            )
            yield (
                str(quad.subject.value),
                str(quad.predicate.value),
                obj_str,
                graph_str,
            )


def _term_to_str(term: Any) -> str:
    """Unwrap a pyoxigraph term to its bare string form.

    ``NamedNode``, ``Literal``, ``BlankNode``, and ``Variable`` all expose
    ``.value`` as the bare lexical (``"M-001"`` rather than the SPARQL
    serialisation ``'"M-001"'``); rdflib's backend returns the same shape,
    so this keeps cross-backend row schemas identical.
    """
    if hasattr(term, "value"):
        return str(term.value)
    return str(term)


def _to_named_node(token: str) -> Any:
    """CURIE / IRI → pyoxigraph NamedNode."""
    import pyoxigraph as _pyoxi

    return _pyoxi.NamedNode(_expand_curie(token))


def _to_object(value: str | int | float | bool) -> Any:
    import pyoxigraph as _pyoxi

    NamedNode = _pyoxi.NamedNode  # noqa: N806 — third-party class re-bound locally
    Literal = _pyoxi.Literal  # noqa: N806 — third-party class re-bound locally
    if isinstance(value, bool):
        return Literal(str(value).lower(), datatype=NamedNode(
            "http://www.w3.org/2001/XMLSchema#boolean",
        ))
    if isinstance(value, int):
        return Literal(str(value), datatype=NamedNode(
            "http://www.w3.org/2001/XMLSchema#integer",
        ))
    if isinstance(value, float):
        return Literal(str(value), datatype=NamedNode(
            "http://www.w3.org/2001/XMLSchema#double",
        ))
    if value.startswith(("http://", "https://", "urn:")):
        return NamedNode(value)
    if ":" in value and value.split(":", 1)[0] in NAMESPACES:
        return NamedNode(_expand_curie(value))
    return Literal(value)


# ---------- plugin entry point ----------

class _OxigraphPlugin:
    """Single-instance StoreBackendPlugin for the oxigraph backend.

    Held by :func:`register` so the same store is reused for the whole
    process (oxigraph keeps an internal in-memory RocksDB)."""

    name = "oxigraph"

    def __init__(self) -> None:
        self._store: OxigraphStore | None = None

    def on_load(self, project_root: str | Path) -> GraphStore:
        if self._store is None:
            self._store = OxigraphStore()
        self._store.load(project_root)
        return self._store

    def on_dispose(self) -> None:
        self._store = None


def register(registry: Any) -> None:
    """Plugin entry point — called by :func:`cataforge.kg.plugin_hooks.load_plugins`."""
    registry.register_store_backend(_OxigraphPlugin())
