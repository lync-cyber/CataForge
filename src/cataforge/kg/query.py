"""`QueryAPI` — read-only SPARQL accessors keyed by SDLC layer.

Sub-PR 5 surface: the methods needed by `_shim.py` and the Group A
call-site migration. The full Pydantic-hydrated surface specified in
task-5 §5.2 lands when SHACL-validated Pydantic round-trip arrives in
a later PR; this module returns flat dicts that mirror the legacy
loader/indexer dict shape so the shim layer is a straight pass-through.

The single-character typed accessors (`feature`, `module`, `component`,
`page`, `api`, `task`, `test_case`) mirror task-5 §5.2 and resolve
Task 5 errata C1 (`api()` / `page()` were missing from the original
task-5 surface; flagged by Task 6 §6.5 #2).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from cataforge.kg._ask import ask
from cataforge.kg._config import KGConfig
from cataforge.kg.ingest.iri import (
    ENTITY_PREFIX_TO_CLASS,
    class_iri,
    entity_iri,
    id_prefix_to_type,
)

if TYPE_CHECKING:
    import pyoxigraph as ox


_CF_NS = "https://cataforge.dev/ontology/"
_ARTIFACT_SCALAR_SLOTS = (
    "entity_id",
    "sort_key",
    "title",
    "description",
    "status",
    "priority",
    "content_hash",
    "source_doc",
    "source_section",
    "authored_by",
    "updated_at",
)


def _term_value(term: Any) -> Any:
    if term is None:
        return None
    return getattr(term, "value", term)


def _row_get(row: Any, var: str) -> Any:
    try:
        return row[var]
    except (KeyError, IndexError):
        return None


@dataclass(frozen=True)
class PlanLoadResult:
    """Result of :meth:`QueryAPI.plan_load`.

    `ordered` and `dropped` are lists of entity-id strings (not URIs);
    the shim layer expects this shape, matching the legacy
    `cataforge.docs.loader.plan_load()` contract.
    """

    ordered: list[str]
    dropped: list[str]
    estimated_tokens: int


class QueryAPI:
    """Read-only SPARQL accessors over a `pyoxigraph.Store`.

    Construction is normally indirect — callers receive an instance as
    `KnowledgeGraph.query`. All methods are synchronous; async callers
    wrap in `asyncio.to_thread`.
    """

    def __init__(self, store: ox.Store, config: KGConfig) -> None:
        self._store = store
        self._config = config

    # ------------------------------------------------------------------
    # Generic lookups
    # ------------------------------------------------------------------

    def entity(self, entity_id_or_uri: str) -> dict[str, Any] | None:
        """Fetch any entity by its entity_id (e.g. ``F-001``) or full URI.

        Returns a flat dict with every scalar slot defined on
        `SoftwareArtifact`, plus the resolved RDF class IRI in `_class`.
        Returns `None` if no triple `?uri cf:entity_id "<id>"` exists.
        """
        if "://" in entity_id_or_uri:
            uri = entity_id_or_uri
            entity_id = uri.rsplit("/", 1)[-1]
        else:
            entity_id = entity_id_or_uri
            uri = entity_iri(entity_id, self._config.base_namespace)
        return self._fetch_by_uri(uri, entity_id)

    def exists(self, entity_id_or_uri: str) -> bool:
        """ASK whether the given entity exists."""
        if "://" in entity_id_or_uri:
            uri = entity_id_or_uri
        else:
            uri = entity_iri(entity_id_or_uri, self._config.base_namespace)
        sparql = (
            f"PREFIX cf: <{self._cf_ns()}> "
            f"ASK {{ <{uri}> cf:entity_id ?eid }}"
        )
        return ask(self._store, sparql)

    # ------------------------------------------------------------------
    # Typed accessors (task-5 §5.2 + errata C1)
    # ------------------------------------------------------------------

    def feature(self, feature_id: str) -> dict[str, Any] | None:
        return self._fetch_typed("Feature", feature_id)

    def module(self, module_id: str) -> dict[str, Any] | None:
        return self._fetch_typed("Module", module_id)

    def component(self, comp_id: str) -> dict[str, Any] | None:
        return self._fetch_typed("Component", comp_id)

    def page(self, page_id: str) -> dict[str, Any] | None:
        return self._fetch_typed("Page", page_id)

    def api(self, api_id: str) -> dict[str, Any] | None:
        return self._fetch_typed("API", api_id)

    def task(self, task_id: str) -> dict[str, Any] | None:
        return self._fetch_typed("Task", task_id)

    def test_case(self, tc_id: str) -> dict[str, Any] | None:
        return self._fetch_typed("TestCase", tc_id)

    def requirement(self, req_id: str) -> dict[str, Any] | None:
        """Fetch any Requirement-layer artifact (Feature / UserStory / Epic)."""
        return self._fetch_subclass("Requirement", req_id)

    # ------------------------------------------------------------------
    # Bulk / cross-cutting
    # ------------------------------------------------------------------

    def all_entities(
        self, *, types: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Enumerate every entity, ordered by sort_key.

        `types` is an optional list of LinkML class names (e.g. ``["Feature"]``);
        when given, only those classes (or their subclasses via
        `rdfs:subClassOf*`) are returned.
        """
        ns = self._cf_ns()
        if types:
            type_filters = " UNION ".join(
                f"{{ ?s a/rdfs:subClassOf* <{class_iri(t, ns)}> }}" for t in types
            )
        else:
            type_filters = (
                "{ ?s a/rdfs:subClassOf* cf:SoftwareArtifact . "
                "FILTER NOT EXISTS { ?s a cf:Project } }"
            )
        sparql = (
            f"PREFIX cf:   <{ns}> "
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
            "SELECT ?s ?entity_id ?sort_key ?title ?status "
            "       ?source_doc ?source_section ?cls "
            "WHERE { "
            f"  {type_filters} "
            "  ?s a ?cls ; "
            "     cf:entity_id ?entity_id ; "
            "     cf:sort_key  ?sort_key ; "
            "     cf:title     ?title . "
            "  OPTIONAL { ?s cf:status         ?status } "
            "  OPTIONAL { ?s cf:source_doc     ?source_doc } "
            "  OPTIONAL { ?s cf:source_section ?source_section } "
            "  FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
            "} "
            "ORDER BY ASC(?sort_key) ASC(?entity_id)"
        )
        out: list[dict[str, Any]] = []
        for row in self._store.query(sparql):
            uri = _term_value(_row_get(row, "s"))
            if uri is None:
                continue
            cls_uri = _term_value(_row_get(row, "cls"))
            cls_name = (
                str(cls_uri).rsplit("/", 1)[-1] if cls_uri else None
            )
            out.append(
                {
                    "uri": str(uri),
                    "entity_id": _strv(_row_get(row, "entity_id")),
                    "sort_key": _strv(_row_get(row, "sort_key")),
                    "title": _strv(_row_get(row, "title")),
                    "status": _strv(_row_get(row, "status")),
                    "source_doc": _strv(_row_get(row, "source_doc")),
                    "source_section": _strv(_row_get(row, "source_section")),
                    "_class": cls_name,
                }
            )
        return out

    def entity_ids(self) -> set[str]:
        """Return the set of every `cf:entity_id` present in the store.

        Used by the doctor `kg_ingestion_completeness` gate to diff KG
        against filesystem-discovered entity IDs.
        """
        ns = self._cf_ns()
        sparql = (
            f"PREFIX cf:   <{ns}> "
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
            "SELECT DISTINCT ?entity_id WHERE { "
            "  ?s a/rdfs:subClassOf* cf:SoftwareArtifact ; "
            "     cf:entity_id ?entity_id . "
            "}"
        )
        return {
            _strv(_row_get(row, "entity_id"))
            for row in self._store.query(sparql)
            if _row_get(row, "entity_id") is not None
        }

    def source_section(self, doc_id: str, anchor: str) -> str | None:
        """Materialize raw Markdown for a section that is not modeled as
        an entity (e.g. PRD §1 intro, arch §1.4 tech-stack narrative).

        Looks up the first artifact whose `cf:source_doc` starts with
        `doc_id`, then slices its on-disk file at the heading matching
        `anchor`. Returns `None` when no source can be located.
        """
        ns = self._cf_ns()
        anchor_lit = anchor.replace("\\", "\\\\").replace('"', '\\"')
        sparql = (
            f"PREFIX cf: <{ns}> "
            "SELECT DISTINCT ?src WHERE { "
            "  ?s cf:source_doc ?src . "
            f'  FILTER(STRSTARTS(STR(?src), "{doc_id}")) '
            "} LIMIT 1"
        )
        rows = list(self._store.query(sparql))
        if not rows:
            return None
        from pathlib import Path  # noqa: PLC0415

        src = _strv(_row_get(rows[0], "src"))
        if not src:
            return None
        path = Path(src)
        if not path.exists():
            return None
        return _slice_section(path.read_text(encoding="utf-8"), anchor_lit)

    # ------------------------------------------------------------------
    # plan_load — token-budget-aware load ordering
    # ------------------------------------------------------------------

    def plan_load(
        self,
        uris_or_ids: list[str],
        token_budget: int,
        *,
        include_related: bool = True,
    ) -> PlanLoadResult:
        """Topologically order the requested entities within a token budget.

        Sub-PR 5 ships a simple variant: deduplicate input, optionally
        expand by `cf:depends_on` 1-hop neighbours, then greedily fit
        within `token_budget` using a flat 200-token-per-entity estimate.
        Anything that does not fit goes to `dropped`. This matches the
        contract of the legacy `cataforge.docs.loader.plan_load()` that
        the shim wraps.
        """
        seeds: list[str] = []
        seen: set[str] = set()
        for raw in uris_or_ids:
            eid = raw.rsplit("/", 1)[-1] if "://" in raw else raw
            if eid in seen:
                continue
            seen.add(eid)
            seeds.append(eid)

        if include_related:
            for eid in list(seeds):
                for dep in self._depends_on(eid):
                    if dep not in seen:
                        seen.add(dep)
                        seeds.append(dep)

        per_entity = 200
        ordered: list[str] = []
        dropped: list[str] = []
        remaining = token_budget
        for eid in seeds:
            if per_entity <= remaining:
                ordered.append(eid)
                remaining -= per_entity
            else:
                dropped.append(eid)
        return PlanLoadResult(
            ordered=ordered,
            dropped=dropped,
            estimated_tokens=per_entity * len(ordered),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _cf_ns(self) -> str:
        return self._config.ontology_namespace.rstrip("/") + "/"

    def _depends_on(self, entity_id: str) -> list[str]:
        ns = self._cf_ns()
        uri = entity_iri(entity_id, self._config.base_namespace)
        sparql = (
            f"PREFIX cf: <{ns}> "
            "SELECT ?dep_id WHERE { "
            f"  <{uri}> cf:depends_on ?dep . "
            "  ?dep cf:entity_id ?dep_id . "
            "} ORDER BY ?dep_id"
        )
        return [
            _strv(_row_get(row, "dep_id"))
            for row in self._store.query(sparql)
            if _row_get(row, "dep_id") is not None
        ]

    def _fetch_typed(self, class_name: str, entity_id: str) -> dict[str, Any] | None:
        uri = entity_iri(entity_id, self._config.base_namespace)
        cls_uri = class_iri(class_name, self._cf_ns())
        sparql = (
            f"PREFIX cf:   <{self._cf_ns()}> "
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
            f"ASK {{ <{uri}> a/rdfs:subClassOf* <{cls_uri}> }}"
        )
        if not ask(self._store, sparql):
            return None
        return self._fetch_by_uri(uri, entity_id)

    def _fetch_subclass(self, parent_class: str, entity_id: str) -> dict[str, Any] | None:
        # Same as _fetch_typed but the type-membership test walks the
        # subclass chain — used by `requirement()` which accepts any of
        # Feature / UserStory / Epic.
        return self._fetch_typed(parent_class, entity_id)

    def _fetch_by_uri(self, uri: str, entity_id: str) -> dict[str, Any] | None:
        ns = self._cf_ns()
        slot_proj = "  ".join(f"?{slot}" for slot in _ARTIFACT_SCALAR_SLOTS)
        slot_clauses = "\n".join(
            f"  OPTIONAL {{ <{uri}> cf:{slot} ?{slot} }}"
            for slot in _ARTIFACT_SCALAR_SLOTS
            if slot != "entity_id"
        )
        sparql = (
            f"PREFIX cf: <{ns}> "
            f"SELECT ?cls {slot_proj} WHERE {{ "
            f"  <{uri}> a ?cls ; cf:entity_id ?entity_id . "
            f"  FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
            f"{slot_clauses}"
            "} LIMIT 1"
        )
        rows = list(self._store.query(sparql))
        if not rows:
            return None
        row = rows[0]
        record: dict[str, Any] = {
            "uri": uri,
            "_class": (
                str(_term_value(_row_get(row, "cls"))).rsplit("/", 1)[-1]
                if _row_get(row, "cls")
                else None
            ),
        }
        for slot in _ARTIFACT_SCALAR_SLOTS:
            record[slot] = _strv(_row_get(row, slot))
        # Ensure the entity_id is always populated even if the SELECT
        # bound it to None (defensive — schema guarantees presence).
        if not record.get("entity_id"):
            record["entity_id"] = entity_id
        return record


def _strv(term: Any) -> Any:
    v = _term_value(term)
    if v is None:
        return None
    return str(v)


def _slice_section(text: str, anchor: str) -> str | None:
    """Return the slice of `text` from the heading matching `anchor` to
    the next sibling heading (or EOF). Anchor matching tolerates the
    common ``§N.M`` form by stripping the leading ``§`` before comparison.
    """
    lines = text.splitlines()
    marker = anchor.lstrip("§").strip()
    start: int | None = None
    end = len(lines)
    for i, line in enumerate(lines):
        if line.startswith("#") and marker in line:
            start = i
            continue
        if start is not None and line.startswith("#") and i > start:
            end = i
            break
    if start is None:
        return None
    return "\n".join(lines[start:end])


__all__ = [
    "PlanLoadResult",
    "QueryAPI",
]
