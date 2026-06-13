"""`QueryAPI` — read-only SPARQL accessors keyed by SDLC layer.

Returns flat dicts that mirror the legacy loader/indexer dict shape so the
shim layer is a straight pass-through.

The typed accessors (`feature`, `module`, `component`, `page`, `api`,
`task`, `test_case`) cover all entity types in the business ontology.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from cataforge.domain.kg._ask import ask
from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _strv,
    _term_value,
    cf_namespace,
    escape_sparql_literal,
    resolve_stored_entity_iri,
    select_rows,
)
from cataforge.domain.kg.ingest.iri import class_iri
from cataforge.utils.md_parse import slice_section

if TYPE_CHECKING:
    import pyoxigraph as ox


_PLAN_LOAD_TOKENS_PER_ENTITY = 200
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


@dataclass(frozen=True)
class PlanLoadResult:
    """Result of :meth:`QueryAPI.plan_load`.

    `ordered` and `dropped` are lists of entity-id strings (not URIs);
    the shim layer expects this shape, matching the legacy
    `cataforge.domain.docs.loader.plan_load()` contract.
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
            uri = resolve_stored_entity_iri(self._store, self._config, entity_id)
        return self._fetch_by_uri(uri, entity_id)

    def exists(self, entity_id_or_uri: str) -> bool:
        """ASK whether the given entity exists."""
        if "://" in entity_id_or_uri:
            uri = entity_id_or_uri
        else:
            uri = resolve_stored_entity_iri(self._store, self._config, entity_id_or_uri)
        sparql = f"PREFIX cf: <{self._cf_ns()}> ASK {{ <{uri}> cf:entity_id ?eid }}"
        return ask(self._store, sparql)

    # ------------------------------------------------------------------
    # Typed accessors
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
        return self._fetch_typed("Requirement", req_id)

    # ------------------------------------------------------------------
    # Bulk / cross-cutting
    # ------------------------------------------------------------------

    def all_entities(self, *, types: list[str] | None = None) -> list[dict[str, Any]]:
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
        for row in select_rows(self._store, sparql):
            uri = _term_value(_row_lookup(row, "s"))
            if uri is None:
                continue
            cls_uri = _term_value(_row_lookup(row, "cls"))
            cls_name = str(cls_uri).rsplit("/", 1)[-1] if cls_uri else None
            out.append(
                {
                    "uri": str(uri),
                    "entity_id": _strv(_row_lookup(row, "entity_id")),
                    "sort_key": _strv(_row_lookup(row, "sort_key")),
                    "title": _strv(_row_lookup(row, "title")),
                    "status": _strv(_row_lookup(row, "status")),
                    "source_doc": _strv(_row_lookup(row, "source_doc")),
                    "source_section": _strv(_row_lookup(row, "source_section")),
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
            v
            for row in select_rows(self._store, sparql)
            if (v := _strv(_row_lookup(row, "entity_id"))) is not None
        }

    def has_documents(self) -> bool:
        """Return whether any `cf:Document` node exists in the store.

        finalize uses this to tell an authored-but-entity-less graph (which
        must still export) from a truly empty md-first graph (which seeds).
        """
        ns = self._cf_ns()
        sparql = f"PREFIX cf: <{ns}> SELECT ?doc WHERE {{ ?doc a cf:Document }} LIMIT 1"
        return any(True for _ in select_rows(self._store, sparql))

    def source_section(self, doc_id: str, anchor: str) -> str | None:
        """Materialize raw Markdown for a section that is not modeled as
        an entity (e.g. PRD §1 intro, arch §1.4 tech-stack narrative).

        Looks up the first artifact whose `cf:source_doc` starts with
        `doc_id`, then slices its on-disk file at the heading matching
        `anchor`. Returns `None` when no source can be located.
        """
        ns = self._cf_ns()
        anchor_lit = escape_sparql_literal(anchor)
        doc_id_lit = escape_sparql_literal(doc_id)
        sparql = (
            f"PREFIX cf: <{ns}> "
            "SELECT DISTINCT ?src WHERE { "
            "  ?s cf:source_doc ?src . "
            f'  FILTER(STRSTARTS(STR(?src), "{doc_id_lit}")) '
            "} LIMIT 1"
        )
        rows = list(select_rows(self._store, sparql))
        if not rows:
            return None
        from pathlib import Path  # noqa: PLC0415

        src = _strv(_row_lookup(rows[0], "src"))
        if not src:
            return None
        path = Path(src)
        if not path.exists():
            return None
        return slice_section(path.read_text(), anchor_lit)

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

        Deduplicates input, optionally expands by `cf:depends_on` 1-hop
        neighbours, then greedily fits within `token_budget` using a flat
        200-token-per-entity estimate. Anything that does not fit goes to
        `dropped`. Matches the contract of the legacy
        `cataforge.domain.docs.loader.plan_load()` that the shim wraps.
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
                for dep in self.depends_on(eid):
                    if dep not in seen:
                        seen.add(dep)
                        seeds.append(dep)

        per_entity = _PLAN_LOAD_TOKENS_PER_ENTITY
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
        return cf_namespace(self._config)

    def depends_on(self, entity_id: str) -> list[str]:
        ns = self._cf_ns()
        uri = resolve_stored_entity_iri(self._store, self._config, entity_id)
        sparql = (
            f"PREFIX cf: <{ns}> "
            "SELECT ?dep_id WHERE { "
            f"  <{uri}> cf:depends_on ?dep . "
            "  ?dep cf:entity_id ?dep_id . "
            "} ORDER BY ?dep_id"
        )
        return [
            v
            for row in select_rows(self._store, sparql)
            if (v := _strv(_row_lookup(row, "dep_id"))) is not None
        ]

    def _fetch_typed(self, class_name: str, entity_id: str) -> dict[str, Any] | None:
        uri = resolve_stored_entity_iri(self._store, self._config, entity_id)
        cls_uri = class_iri(class_name, self._cf_ns())
        sparql = (
            f"PREFIX cf:   <{self._cf_ns()}> "
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
            f"ASK {{ <{uri}> a/rdfs:subClassOf* <{cls_uri}> }}"
        )
        if not ask(self._store, sparql):
            return None
        return self._fetch_by_uri(uri, entity_id)

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
        rows = list(select_rows(self._store, sparql))
        if not rows:
            return None
        row = rows[0]
        record: dict[str, Any] = {
            "uri": uri,
            "_class": (
                str(_term_value(_row_lookup(row, "cls"))).rsplit("/", 1)[-1]
                if _row_lookup(row, "cls")
                else None
            ),
        }
        for slot in _ARTIFACT_SCALAR_SLOTS:
            record[slot] = _strv(_row_lookup(row, slot))
        # Ensure the entity_id is always populated even if the SELECT
        # bound it to None (defensive — schema guarantees presence).
        if not record.get("entity_id"):
            record["entity_id"] = entity_id
        return record


__all__ = [
    "PlanLoadResult",
    "QueryAPI",
]
