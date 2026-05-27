"""`TraceAPI` — traceability chain queries.

Sub-PR 5 surface: enough to back the doc-review §6.4 A13 bidirectional
coverage rewrite, sprint-review's `targets_artifact` back-reference need,
and the shim layer's `legacy_validate_report()` stale-dep query. Returns
flat dicts and lists; the typed `TraceChain` dataclass from task-5 §5.2
lands once `_models_core` Pydantic round-trip arrives.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from cataforge.kg._config import KGConfig
from cataforge.kg._sparql_utils import _row_lookup, _strv, _term_value
from cataforge.kg.ingest.iri import entity_iri

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
    """Subset of task-5 §5.2 TraceChain — only the fields sub-PR 5
    consumers need. Lists hold entity_id strings.
    """

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
    # §6.4 A13 — bidirectional coverage rewrite
    # ------------------------------------------------------------------

    def bidirectional_coverage(self) -> list[CoverageRow]:
        """Return one row per Feature with implementation + test status.

        Replaces `doc-review check_bidirectional_coverage()` regex pass
        per Task 6 §6.4 A13. A Feature is covered iff some artifact
        asserts `cf:implements` on it AND some TestCase reaches it via
        `cf:verifies+` (transitive). Mention-in-prose no longer counts.
        """
        ns = self._cf_ns()
        sparql = (
            f"PREFIX cf:   <{ns}> "
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
            "SELECT ?feature_id ?title "
            "       (BOUND(?impl) AS ?has_impl) "
            "       (BOUND(?tc)   AS ?has_test) "
            "WHERE { "
            "  ?feature a cf:Feature ; "
            "           cf:entity_id ?feature_id ; "
            "           cf:title     ?title . "
            "  OPTIONAL { "
            "    ?impl_node cf:implements ?feature . "
            "    ?impl_node a ?impl_class . "
            "    ?impl_class rdfs:subClassOf* cf:SoftwareArtifact . "
            "    BIND(?impl_node AS ?impl) "
            "  } "
            "  OPTIONAL { "
            "    ?tc a cf:TestCase ; cf:verifies+ ?feature . "
            "  } "
            "} ORDER BY ?feature_id"
        )
        out: list[CoverageRow] = []
        for row in self._store.query(sparql):
            fid = _strv(_row_lookup(row, "feature_id"))
            if fid is None:
                continue
            out.append(
                CoverageRow(
                    feature_id=fid,
                    title=_strv(_row_lookup(row, "title")),
                    has_impl=_bool_term(_row_lookup(row, "has_impl")),
                    has_test=_bool_term(_row_lookup(row, "has_test")),
                )
            )
        return out

    def coverage(self, feature_id: str) -> dict[str, Any]:
        """Coverage status for a single Feature.

        Returns ``{"has_impl": bool, "has_test": bool, "status":
        "full"|"partial"|"none"}``.
        """
        ns = self._cf_ns()
        uri = entity_iri(feature_id, self._config.base_namespace)
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
        rows = list(self._store.query(sparql))
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
    # §6.4 A7 — sprint-review chain (CODE-REVIEW back-reference)
    # ------------------------------------------------------------------

    def from_requirement(
        self,
        entity_id: str,
        *,
        direction: Literal["downstream", "upstream", "both"] = "downstream",
    ) -> TraceChain:
        """Build a flat TraceChain rooted at `entity_id`.

        Downstream traverses: `cf:implements`/`cf:realizes`/`cf:verifies`/
        `cf:satisfies`/`cf:reviewed_by`. Upstream walks the inverses. The
        implementation is a fan-out single-query CONSTRUCT-shape walker;
        it is not transitive across more than one hop in sub-PR 5 — the
        Group A consumers only need one-hop fan-out at this stage.
        """
        ns = self._cf_ns()
        uri = entity_iri(entity_id, self._config.base_namespace)

        if direction in ("downstream", "both"):
            downstream_rows = list(
                self._store.query(
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
                    "  } "
                    "  FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
                    "}"
                )
            )
        else:
            downstream_rows = []

        if direction in ("upstream", "both"):
            upstream_rows = list(
                self._store.query(
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
                    "  } "
                    "  FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
                    "}"
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
            chain.coverage_status = (
                "full" if chain.test_cases else "partial"
            )
        elif chain.test_cases:
            chain.coverage_status = "partial"
        else:
            chain.coverage_status = "none"
        return chain

    # ------------------------------------------------------------------
    # §6.5 #3 — stale dependency detector (legacy_validate_report)
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
        for row in self._store.query(sparql):
            a = _strv(_row_lookup(row, "a_id"))
            b = _strv(_row_lookup(row, "b_id"))
            if a is not None and b is not None:
                out.append((a, b))
        return out

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _cf_ns(self) -> str:
        return self._config.ontology_namespace.rstrip("/") + "/"


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
