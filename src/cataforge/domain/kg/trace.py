"""`TraceAPI` — traceability chain queries.

Returns flat dicts and lists for bidirectional coverage, sprint-review
back-references, and stale-dep queries. The typed `TraceChain` dataclass
is used by consumers that need structured traversal results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _strv,
    _term_value,
    cf_namespace,
    resolve_stored_entity_iri,
    select_rows,
)

if TYPE_CHECKING:
    import pyoxigraph as ox


@dataclass(frozen=True)
class CoverageRow:
    """One row of :meth:`TraceAPI.bidirectional_coverage`."""

    feature_id: str
    title: str | None
    has_impl: bool
    has_test: bool


@dataclass
class TraceChain:
    """Flat traceability chain rooted at one entity. Lists hold entity_id strings."""

    root_id: str
    requirements: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    test_cases: list[str] = field(default_factory=list)
    review_reports: list[str] = field(default_factory=list)
    coverage_status: Literal["full", "partial", "none"] = "none"
    chain_breaks: list[tuple[str, str, str]] = field(default_factory=list)


class TraceAPI:
    """Traceability queries over a `pyoxigraph.Store`."""

    def __init__(self, store: ox.Store, config: KGConfig) -> None:
        self._store = store
        self._config = config

    # ------------------------------------------------------------------
    # Bidirectional coverage
    # ------------------------------------------------------------------

    def bidirectional_coverage(self) -> list[CoverageRow]:
        """Return one row per Feature with implementation + test status.

        A Feature is covered iff some artifact asserts `cf:implements` on it
        AND some TestCase reaches it via `cf:verifies+` (transitive).
        Mention-in-prose does not count.

        Two separate SELECT queries are merged on the Python side to avoid
        the SPARQL 1.1 cartesian-product semantics that parallel OPTIONAL
        blocks produce when N impl-nodes x M test-cases both bind.
        """
        ns = self._cf_ns()
        prefix = f"PREFIX cf:   <{ns}> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "

        # Pass 1: feature metadata + impl presence
        impl_sparql = (
            prefix + "SELECT DISTINCT ?feature_id ?title "
            "WHERE { "
            "  ?feature a cf:Feature ; "
            "           cf:entity_id ?feature_id ; "
            "           cf:title     ?title . "
            "} ORDER BY ?feature_id"
        )
        titles: dict[str, str | None] = {}
        for row in select_rows(self._store, impl_sparql):
            fid = _strv(_row_lookup(row, "feature_id"))
            if fid is not None:
                titles[fid] = _strv(_row_lookup(row, "title"))

        # Pass 2: which features have at least one impl artifact
        has_impl_sparql = (
            prefix + "SELECT DISTINCT ?feature_id WHERE { "
            "  ?feature a cf:Feature ; cf:entity_id ?feature_id . "
            "  FILTER EXISTS { "
            "    ?impl_node cf:implements ?feature . "
            "    ?impl_node a ?impl_class . "
            "    ?impl_class rdfs:subClassOf* cf:SoftwareArtifact . "
            "  } "
            "}"
        )
        has_impl: set[str] = set()
        for row in select_rows(self._store, has_impl_sparql):
            fid = _strv(_row_lookup(row, "feature_id"))
            if fid is not None:
                has_impl.add(fid)

        # Pass 3: which features have at least one verifying TestCase
        has_test_sparql = (
            prefix + "SELECT DISTINCT ?feature_id WHERE { "
            "  ?feature a cf:Feature ; cf:entity_id ?feature_id . "
            "  FILTER EXISTS { ?tc a cf:TestCase ; cf:verifies+ ?feature } "
            "}"
        )
        has_test: set[str] = set()
        for row in select_rows(self._store, has_test_sparql):
            fid = _strv(_row_lookup(row, "feature_id"))
            if fid is not None:
                has_test.add(fid)

        return [
            CoverageRow(
                feature_id=fid,
                title=titles[fid],
                has_impl=fid in has_impl,
                has_test=fid in has_test,
            )
            for fid in sorted(titles)
        ]

    def coverage(self, feature_id: str) -> dict[str, Any]:
        """Coverage status for a single Feature.

        Returns ``{"has_impl": bool, "has_test": bool, "status":
        "full"|"partial"|"none"}``.
        """
        ns = self._cf_ns()
        uri = resolve_stored_entity_iri(self._store, self._config, feature_id)
        sparql = (
            f"PREFIX cf:   <{ns}> "
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
            "SELECT (BOUND(?impl) AS ?has_impl) "
            "       (BOUND(?tc)   AS ?has_test) "
            "WHERE { "
            "  OPTIONAL { "
            f"    ?impl cf:implements <{uri}> . "
            "    ?impl a ?impl_class . "
            "    ?impl_class rdfs:subClassOf* cf:SoftwareArtifact . "
            "  } "
            "  OPTIONAL { "
            f"    ?tc a cf:TestCase ; cf:verifies+ <{uri}> . "
            "  } "
            "}"
        )
        rows = list(select_rows(self._store, sparql))
        if not rows:
            return {"has_impl": False, "has_test": False, "status": "none"}
        row = rows[0]
        has_impl = _bool_term(_row_lookup(row, "has_impl"))
        has_test = _bool_term(_row_lookup(row, "has_test"))
        if has_impl and has_test:
            status = "full"
        elif has_impl or has_test:
            status = "partial"
        else:
            status = "none"
        return {"has_impl": has_impl, "has_test": has_test, "status": status}

    # ------------------------------------------------------------------
    # Sprint-review chain
    # ------------------------------------------------------------------

    def from_requirement(
        self,
        entity_id: str,
        *,
        direction: Literal["downstream", "upstream", "both"] = "downstream",
    ) -> TraceChain:
        """Build a flat TraceChain rooted at ``entity_id``.

        Downstream traverses: ``cf:implements`` / ``cf:realizes`` /
        ``cf:verifies`` / ``cf:satisfies`` / ``cf:part_of`` (in-edges —
        sub-entities such as AcceptanceCriteria).  Upstream walks the
        inverses plus ``cf:reviewed_by``.  Single-hop fan-out only.
        """
        ns = self._cf_ns()
        uri = resolve_stored_entity_iri(self._store, self._config, entity_id)

        if direction in ("downstream", "both"):
            downstream_rows = list(
                select_rows(
                    self._store,
                    f"PREFIX cf: <{ns}> "
                    "SELECT ?neighbour_id ?cls WHERE { "
                    "  { "
                    f"    ?n cf:implements <{uri}> . "
                    "    ?n a ?cls ; cf:entity_id ?neighbour_id . "
                    "  } UNION { "
                    f"    ?n a cf:TestCase ; cf:verifies <{uri}> ; "
                    "       cf:entity_id ?neighbour_id . "
                    "    ?n a ?cls . "
                    "  } UNION { "
                    f"    ?n cf:satisfies <{uri}> . "
                    "    ?n a ?cls ; cf:entity_id ?neighbour_id . "
                    "  } UNION { "
                    f"    ?n cf:realizes <{uri}> . "
                    "    ?n a ?cls ; cf:entity_id ?neighbour_id . "
                    "  } UNION { "
                    f"    ?n cf:part_of <{uri}> . "
                    "    ?n a ?cls ; cf:entity_id ?neighbour_id . "
                    "  } "
                    "  FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
                    "}",
                )
            )
        else:
            downstream_rows = []

        if direction in ("upstream", "both"):
            upstream_rows = list(
                select_rows(
                    self._store,
                    f"PREFIX cf: <{ns}> "
                    "SELECT ?neighbour_id ?cls WHERE { "
                    "  { "
                    f"    <{uri}> cf:implements ?n . "
                    "    ?n a ?cls ; cf:entity_id ?neighbour_id . "
                    "  } UNION { "
                    f"    <{uri}> cf:verifies ?n . "
                    "    ?n a ?cls ; cf:entity_id ?neighbour_id . "
                    "  } UNION { "
                    f"    <{uri}> cf:satisfies ?n . "
                    "    ?n a ?cls ; cf:entity_id ?neighbour_id . "
                    "  } UNION { "
                    f"    <{uri}> cf:realizes ?n . "
                    "    ?n a ?cls ; cf:entity_id ?neighbour_id . "
                    "  } UNION { "
                    f"    <{uri}> cf:reviewed_by ?n . "
                    "    ?n a ?cls ; cf:entity_id ?neighbour_id . "
                    "  } UNION { "
                    f"    <{uri}> cf:part_of ?n . "
                    "    ?n a ?cls ; cf:entity_id ?neighbour_id . "
                    "  } "
                    "  FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
                    "}",
                )
            )
        else:
            upstream_rows = []

        chain = TraceChain(root_id=entity_id)
        for row in downstream_rows + upstream_rows:
            neighbour_id = _strv(_row_lookup(row, "neighbour_id"))
            cls = _term_value(_row_lookup(row, "cls"))
            if neighbour_id is None or cls is None:
                continue
            cls_name = str(cls).rsplit("/", 1)[-1]
            _push_by_class(chain, cls_name, neighbour_id)

        if chain.modules or chain.components or chain.tasks:
            chain.coverage_status = "full" if chain.test_cases else "partial"
        elif chain.test_cases:
            chain.coverage_status = "partial"
        else:
            chain.coverage_status = "none"
        return chain

    # ------------------------------------------------------------------
    # Stale dependency detector
    # ------------------------------------------------------------------

    def stale_dependencies(self) -> list[tuple[str, str]]:
        """Return `(from_entity_id, to_entity_id)` pairs whose
        `cf:content_hash` differs between subject and dependency.
        """
        ns = self._cf_ns()
        sparql = (
            f"PREFIX cf: <{ns}> "
            "SELECT ?a_id ?b_id WHERE { "
            "  ?a cf:depends_on ?b ; "
            "     cf:entity_id   ?a_id ; "
            "     cf:content_hash ?h_a . "
            "  ?b cf:entity_id   ?b_id ; "
            "     cf:content_hash ?h_b . "
            "  FILTER(?h_a != ?h_b) "
            "} ORDER BY ?a_id ?b_id"
        )
        out: list[tuple[str, str]] = []
        for row in select_rows(self._store, sparql):
            a = _strv(_row_lookup(row, "a_id"))
            b = _strv(_row_lookup(row, "b_id"))
            if a is not None and b is not None:
                out.append((a, b))
        return out

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _cf_ns(self) -> str:
        return cf_namespace(self._config)


def _bool_term(term: Any) -> bool:
    """Coerce a SPARQL BOUND() result to a real Python bool.

    pyoxigraph returns a Literal with xsd:boolean datatype. `bool(term)`
    is true for *any* Literal instance, so we have to inspect `.value`.
    """
    if term is None:
        return False
    val = getattr(term, "value", term)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1")
    return bool(val)


def _push_by_class(chain: TraceChain, cls_name: str, entity_id: str) -> None:
    bucket = _CLASS_TO_BUCKET.get(cls_name)
    if bucket is None:
        return
    target: list[str] = getattr(chain, bucket)
    if entity_id not in target:
        target.append(entity_id)


_CLASS_TO_BUCKET: dict[str, str] = {
    "Feature": "requirements",
    "UserStory": "requirements",
    "Epic": "requirements",
    "AcceptanceCriteria": "acceptance_criteria",
    "Module": "modules",
    "Component": "components",
    "Task": "tasks",
    "Subtask": "tasks",
    "TestCase": "test_cases",
    "ReviewReport": "review_reports",
}


__all__ = [
    "CoverageRow",
    "TraceAPI",
    "TraceChain",
]
