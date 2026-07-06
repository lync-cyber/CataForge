"""Per-doc_type drift detector between Markdown sources and the KG store.

Implements `cataforge kg drift-check`. For every doc_type in
`KGConfig.kg_active_doc_types`, the reconciler:

1. Scans `docs/{subdir}/*.md` using the same ingest pipeline as
   `cataforge kg import` (`scan_business_docs` → `extract_entities`
   → `extract_relations`).
2. Pulls the corresponding entities and traceability triples from the
   KG, attributed to a doc_type by the `cf:source_doc` literal of each
   entity (relations inherit their subject's source_doc).
3. Computes symmetric difference on entity_ids and on
   `(subject, predicate_curie, object)` triples.
4. Returns a structured report; non-empty divergence sets are surfaced
   as `missing_*` (FS-only) and `ghost_*` (KG-only) lists.

The doctor `kg_ingestion_completeness` gate runs an entity-only variant
of this check at deploy time; `reconcile` is the periodic operational
sweep that additionally covers relations.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

from cataforge.domain.docs.index_ops import _load_doc_type_map
from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._dispatch import (
    context_mode,
    custom_entity_prefixes,
    definition_authority,
)
from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _strv,
    assert_safe_iri,
    cf_namespace,
    curie_for_iri,
    escape_sparql_literal,
    select_rows,
)
from cataforge.domain.kg.authority import (
    DRIFT_CONFLICT,
    DRIFT_GRAPH_AHEAD,
    DRIFT_HUMAN_EDIT,
    DRIFT_IN_SYNC,
    DRIFT_NEVER_EXPORTED,
    REMEDIATE_MANUAL,
    REMEDIATE_NONE,
    ModePolicy,
)
from cataforge.domain.kg.export.document_pipeline import (
    EXPORTED_CONTENT_HASH_SLOT,
    _covered_source_docs,
    _list_documents,
    render_document,
)
from cataforge.domain.kg.ingest.entity_extract import build_prefix_registry, extract_entities
from cataforge.domain.kg.ingest.iri import ENTITY_PREFIX_TO_CLASS, SUBORDINATE_CLASSES
from cataforge.domain.kg.ingest.relation_extract import extract_relations
from cataforge.domain.kg.ingest.scan import scan_business_docs
from cataforge.domain.kg.ingest.structure_extract import extract_structure
from cataforge.domain.kg.section_sync import desynced_tile_sections

if TYPE_CHECKING:
    import pyoxigraph as ox


# Triple-key form used for set diffing. CURIE-normalized predicate so
# the FS-side `cf:implements` and the KG-side full IRI compare equal.
RelKey = tuple[str, str, str]  # (subject_entity_id, predicate_curie, object_entity_id)

# Structural / scoping edges between entities that are NOT source-derived
# traceability relations, so they must not surface as reconcile ghosts.
# `cf:part_of` links a subordinate entity to its owning parent (written by the
# ingest writer, never extracted from xref prose).
_NON_TRACEABILITY_PREDICATES: frozenset[str] = frozenset({"cf:belongs_to_project", "cf:part_of"})

# Object-property slots an xref can produce; mirrors validate's
# `cf:*-target-exists` shapes. An edge on one of these whose object resolves to
# no typed entity node is a dangling-target ghost (a renamed/deleted target
# leaves the edge behind), invisible to the entity_id-keyed relation diff.
_TRACEABILITY_SLOTS: tuple[str, ...] = (
    "implements",
    "satisfies",
    "verifies",
    "realizes",
    "delivers",
    "affects",
    "depends_on",
)


@dataclass
class PerDocTypeReport:
    """Reconciliation outcome for a single doc_type."""

    doc_type: str
    missing_entities: list[str] = field(default_factory=list)
    ghost_entities: list[str] = field(default_factory=list)
    missing_relations: list[RelKey] = field(default_factory=list)
    ghost_relations: list[RelKey] = field(default_factory=list)
    enrichment_relations: list[RelKey] = field(default_factory=list)
    orphan_relations: list[RelKey] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)
    ghost_sections: list[str] = field(default_factory=list)

    @property
    def divergence_count(self) -> int:
        """True-drift count. ``enrichment_relations`` — KG-only edges whose
        home document is content-synced with its render, i.e. graph
        enrichment with no Markdown serialization — are acknowledge-only and
        excluded.
        """
        return (
            len(self.missing_entities)
            + len(self.ghost_entities)
            + len(self.missing_relations)
            + len(self.ghost_relations)
            + len(self.orphan_relations)
            + len(self.missing_sections)
            + len(self.ghost_sections)
        )

    @property
    def missing_count(self) -> int:
        return len(self.missing_entities) + len(self.missing_relations) + len(self.missing_sections)

    @property
    def ghost_count(self) -> int:
        return len(self.ghost_entities) + len(self.ghost_relations) + len(self.ghost_sections)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_type": self.doc_type,
            "missing_entities": sorted(self.missing_entities),
            "ghost_entities": sorted(self.ghost_entities),
            "missing_relations": [list(t) for t in sorted(self.missing_relations)],
            "ghost_relations": [list(t) for t in sorted(self.ghost_relations)],
            "enrichment_relations": [list(t) for t in sorted(self.enrichment_relations)],
            "orphan_relations": [list(t) for t in sorted(self.orphan_relations)],
            "missing_sections": sorted(self.missing_sections),
            "ghost_sections": sorted(self.ghost_sections),
            "divergence_count": self.divergence_count,
        }


@dataclass
class DocumentDriftRecord:
    """Drift verdict for one Document node, keyed by its source path.

    ``desynced_sections`` flags graph-internal tile-cover violations: Section
    nodes whose body disagrees with the level-2 tile that embeds them. The
    export renders the tile while section reads serve the node, so such a
    document can triage ``in_sync`` yet hold revisions that never export —
    it fails the gate and needs manual re-authoring or a re-ingest.
    """

    source_path: str
    doc_id: str
    state: str
    remediation: str = REMEDIATE_NONE
    desynced_sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "doc_id": self.doc_id,
            "state": self.state,
            "remediation": self.remediation,
            "desynced_sections": list(self.desynced_sections),
        }


def _classify_document_drift(file_hash: str | None, baseline: str | None, render_hash: str) -> str:
    """Decide a Document's drift state from its three content hashes.

    ``baseline`` absent → the graph never exported this document. A deleted
    file (``file_hash`` None) with a known baseline reads as graph-ahead: the
    graph still holds content the disk no longer reflects.
    """
    if baseline is None:
        return DRIFT_NEVER_EXPORTED
    if file_hash is None:
        return DRIFT_GRAPH_AHEAD
    file_matches = file_hash == baseline
    render_matches = render_hash == baseline
    if file_matches and render_matches:
        return DRIFT_IN_SYNC
    if not file_matches and render_matches:
        return DRIFT_HUMAN_EDIT
    if file_matches and not render_matches:
        return DRIFT_GRAPH_AHEAD
    return DRIFT_CONFLICT


def _document_baseline(store: ox.Store, config: KGConfig, doc_iri: str) -> str | None:
    """Return a Document's `cf:exported_content_hash`, or None when unset."""
    ns = cf_namespace(config)
    safe = assert_safe_iri(doc_iri)
    slot = EXPORTED_CONTENT_HASH_SLOT.split(":", 1)[1]
    sparql = f"PREFIX cf: <{ns}> SELECT ?h WHERE {{ <{safe}> cf:{slot} ?h }} LIMIT 1"
    for row in select_rows(store, sparql):
        return _strv(_row_lookup(row, "h"))
    return None


@dataclass
class _DocTriage:
    """One Document's hash triage before remediation is assigned."""

    source_path: str
    doc_iri: str
    doc_type: str
    source_doc: str
    state: str
    synced: bool


def _hash_triage(store: ox.Store, project_root: Path, config: KGConfig) -> list[_DocTriage]:
    """Three-way hash triage for every `cf:source_path`-bearing Document.

    ``synced`` is true when the on-disk bytes equal the fresh render — the
    Markdown carries nothing the graph's serialization lacks, so KG-only
    edges homed in that document are enrichment, not drift.
    """
    ns = cf_namespace(config)
    out: list[_DocTriage] = []
    for doc in _list_documents(store, ns):
        source_path = doc["source_path"]
        on_disk = project_root / source_path
        file_hash = hashlib.sha256(on_disk.read_bytes()).hexdigest() if on_disk.is_file() else None
        baseline = _document_baseline(store, config, doc["doc_iri"])
        render_hash = hashlib.sha256(render_document(store, ns, doc).encode("utf-8")).hexdigest()
        out.append(
            _DocTriage(
                source_path=source_path,
                doc_iri=doc["doc_iri"],
                doc_type=doc["doc_type"],
                source_doc=doc["source_doc"],
                state=_classify_document_drift(file_hash, baseline, render_hash),
                synced=file_hash is not None and file_hash == render_hash,
            )
        )
    out.sort(key=lambda t: t.source_path)
    return out


@dataclass
class ReconcileReport:
    """Aggregate reconciliation outcome across every active doc_type."""

    timestamp: str
    active_doc_types: list[str]
    per_doc_type: dict[str, PerDocTypeReport] = field(default_factory=dict)
    mode: str = "graph"
    documents: list[DocumentDriftRecord] = field(default_factory=list)

    @property
    def overall_divergence_count(self) -> int:
        return sum(r.divergence_count for r in self.per_doc_type.values())

    @property
    def document_drift_count(self) -> int:
        """Documents whose three-way triage is anything but ``in_sync``.

        Independent of ``overall_divergence_count`` — the id-set diff and the
        content triage are orthogonal drift signals.
        """
        return sum(1 for d in self.documents if d.state != DRIFT_IN_SYNC)

    @property
    def section_desync_count(self) -> int:
        """Documents holding graph-internal tile-cover violations."""
        return sum(1 for d in self.documents if d.desynced_sections)

    @property
    def enrichment_count(self) -> int:
        return sum(len(r.enrichment_relations) for r in self.per_doc_type.values())

    @property
    def ok(self) -> bool:
        """Authoritative pass/fail, by mode.

        ``graph`` is canonical with Markdown as a lossy export, so the
        document-level three-way triage is the truth and the per-doc_type
        symmetric diff is demoted to diagnostics (its FS re-extraction
        round-trip yields false positives). The non-graph fallback uses the
        symmetric diff directly.
        """
        if self.mode == "graph":
            return self.document_drift_count == 0 and self.section_desync_count == 0
        return self.overall_divergence_count == 0

    @property
    def gate_summary(self) -> str:
        """Human-facing failure detail naming the count ``ok`` was decided on."""
        if self.mode == "graph":
            return (
                f"{self.document_drift_count} document(s) drifted, "
                f"{self.section_desync_count} with desynced sections"
            )
        return f"{self.overall_divergence_count} divergence(s)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "active_doc_types": self.active_doc_types,
            "per_doc_type": {k: v.to_dict() for k, v in sorted(self.per_doc_type.items())},
            "overall_divergence_count": self.overall_divergence_count,
            "enrichment_count": self.enrichment_count,
            "ok": self.ok,
            "mode": self.mode,
            "documents": [d.to_dict() for d in self.documents],
            "document_drift_count": self.document_drift_count,
        }


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scope_key(entity_id: str, class_name: str | None, parent_id: str | None) -> str:
    """Identity used for entity reconciliation: parent-scoped when subordinate."""
    if class_name in SUBORDINATE_CLASSES and parent_id:
        return f"{parent_id}/{entity_id}"
    return entity_id


def _is_subordinate_id(entity_id: str) -> bool:
    """True when ``entity_id``'s prefix maps to a subordinate class (e.g. AC)."""
    return ENTITY_PREFIX_TO_CLASS.get(entity_id.split("-", 1)[0]) in SUBORDINATE_CLASSES


def _is_entity_card(doc: Any) -> bool:
    """True for a per-entity card export (frontmatter carries ``entity_id``).

    Cards are a derived KG→Markdown rendering for orphan entities, not a
    Document-backed source file; their link-style refs and render-only sections
    cannot round-trip back through the ingest scanner.
    """
    return "entity_id" in getattr(doc, "frontmatter", {})


def _kg_entities_for_doc_ids(store: ox.Store, config: KGConfig, doc_ids: set[str]) -> set[str]:
    """Return scope keys in KG whose `cf:source_doc` is one of `doc_ids`.

    Subordinate nodes are keyed `parent/entity_id` (parent recovered via
    `cf:part_of`), matching the FS-side `ExtractedEntity.scope_key`, so a
    parent-scoped AC reconciles instead of colliding on the bare id.
    """
    if not doc_ids:
        return set()
    ns = cf_namespace(config)
    values_clause = " ".join(f'"{escape_sparql_literal(d)}"' for d in sorted(doc_ids))
    sparql = (
        f"PREFIX cf: <{ns}> "
        "SELECT DISTINCT ?entity_id ?cls ?parent_id WHERE { "
        f"  VALUES ?src {{ {values_clause} }} "
        "  ?s a ?cls ; "
        "     cf:entity_id ?entity_id ; "
        "     cf:source_doc ?src . "
        "  OPTIONAL { ?s cf:part_of ?p . ?p cf:entity_id ?parent_id . } "
        "  FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
        "}"
    )
    out: set[str] = set()
    for row in select_rows(store, sparql):
        eid = _strv(_row_lookup(row, "entity_id"))
        if eid is None:
            continue
        cls_iri = _strv(_row_lookup(row, "cls"))
        cls_name = cls_iri.rsplit("/", 1)[-1] if cls_iri else None
        parent_id = _strv(_row_lookup(row, "parent_id"))
        out.add(_scope_key(eid, cls_name, parent_id))
    return out


def _kg_relations_with_homes(
    store: ox.Store, config: KGConfig, doc_ids: set[str]
) -> dict[RelKey, set[str]]:
    """Return `(s_id, predicate_curie, o_id)` triples mapped to the subject's
    home `cf:source_doc` values, restricted to subjects homed in `doc_ids`.

    Both subject and object are returned as entity_id strings so the
    diff against FS-extracted relations is direct. Edges to objects
    that lack a `cf:entity_id` literal are skipped (they should be
    caught by `kg validate` xref-target shape).
    """
    if not doc_ids:
        return {}
    ns = cf_namespace(config)
    values_clause = " ".join(f'"{escape_sparql_literal(d)}"' for d in sorted(doc_ids))
    sparql = (
        f"PREFIX cf: <{ns}> "
        "SELECT ?s_id ?p ?o_id ?src WHERE { "
        f"  VALUES ?src {{ {values_clause} }} "
        "  ?s cf:entity_id ?s_id ; "
        "     cf:source_doc ?src ; "
        "     ?p ?o . "
        "  ?o cf:entity_id ?o_id . "
        f'  FILTER(STRSTARTS(STR(?p), "{ns}")) '
        # ?o cf:entity_id ?o_id above already filters to object-property
        # edges, so this branch only sees traceability predicates.
        "}"
    )
    out: dict[RelKey, set[str]] = {}
    for row in select_rows(store, sparql):
        s_id = _strv(_row_lookup(row, "s_id"))
        p_iri = _strv(_row_lookup(row, "p"))
        o_id = _strv(_row_lookup(row, "o_id"))
        src = _strv(_row_lookup(row, "src"))
        if s_id is None or p_iri is None or o_id is None:
            continue
        curie = curie_for_iri(p_iri, ns)
        if curie in _NON_TRACEABILITY_PREDICATES:
            continue
        homes = out.setdefault((s_id, curie, o_id), set())
        if src is not None:
            homes.add(src)
    return out


def _kg_orphan_relations_for_doc_ids(
    store: ox.Store, config: KGConfig, doc_ids: set[str]
) -> set[RelKey]:
    """Traceability edges whose subject is in `doc_ids` but whose object
    resolves to no typed entity node.

    `_kg_relations_for_doc_ids` inner-joins the object's `cf:entity_id`, so an
    edge to a renamed/deleted target silently drops out of the relation diff
    and never surfaces as a ghost. This mirrors validate's `cf:*-target-exists`
    detection (object has no `rdf:type`) keyed by the subject's `cf:source_doc`
    so the dangling-target edge counts toward divergence. The object id is
    recovered from its instance IRI for a printable, repair-resolvable key.
    """
    if not doc_ids:
        return set()
    ns = cf_namespace(config)
    values_clause = " ".join(f'"{escape_sparql_literal(d)}"' for d in sorted(doc_ids))
    slot_clause = " ".join(f"cf:{slot}" for slot in _TRACEABILITY_SLOTS)
    sparql = (
        f"PREFIX cf: <{ns}> "
        "SELECT ?s_id ?p ?o WHERE { "
        f"  VALUES ?src {{ {values_clause} }} "
        f"  VALUES ?p {{ {slot_clause} }} "
        "  ?s cf:entity_id ?s_id ; "
        "     cf:source_doc ?src ; "
        "     ?p ?o . "
        "  FILTER(isIRI(?o)) "
        "  FILTER NOT EXISTS { ?o a ?o_cls } "
        "}"
    )
    out: set[RelKey] = set()
    for row in select_rows(store, sparql):
        s_id = _strv(_row_lookup(row, "s_id"))
        p_iri = _strv(_row_lookup(row, "p"))
        o_iri = _strv(_row_lookup(row, "o"))
        if s_id is None or p_iri is None or o_iri is None:
            continue
        out.add((s_id, curie_for_iri(p_iri, ns), _entity_id_from_iri(o_iri, config.base_namespace)))
    return out


def _entity_id_from_iri(iri: str, base_namespace: str) -> str:
    """Recover an entity_id (or `parent/entity_id`) from its instance IRI."""
    base = base_namespace if base_namespace.endswith("/") else base_namespace + "/"
    tail = iri[len(base) :] if iri.startswith(base) else iri
    return unquote(tail)


def _kg_sections_for_doc_ids(store: ox.Store, config: KGConfig, doc_ids: set[str]) -> set[str]:
    """Return `cf:section_anchor` values of Section nodes whose
    `cf:source_doc` is one of `doc_ids`."""
    if not doc_ids:
        return set()
    ns = cf_namespace(config)
    values_clause = " ".join(f'"{escape_sparql_literal(d)}"' for d in sorted(doc_ids))
    sparql = (
        f"PREFIX cf: <{ns}> "
        "SELECT DISTINCT ?anchor WHERE { "
        f"  VALUES ?src {{ {values_clause} }} "
        "  ?s a cf:Section ; "
        "     cf:section_anchor ?anchor ; "
        "     cf:source_doc ?src . "
        "}"
    )
    out: set[str] = set()
    for row in select_rows(store, sparql):
        anchor = _strv(_row_lookup(row, "anchor"))
        if anchor is not None:
            out.add(anchor)
    return out


def _split_ghost_relations(
    ghost_keys: set[RelKey],
    rel_homes: dict[RelKey, set[str]],
    synced_src_docs: set[str],
) -> tuple[list[RelKey], list[RelKey]]:
    """Split KG-only edges into (true ghosts, enrichment).

    An edge homed exclusively in content-synced documents has no Markdown
    serialization by construction — graph enrichment, not drift.
    """
    ghosts: list[RelKey] = []
    enrichment: list[RelKey] = []
    for key in ghost_keys:
        homes = rel_homes.get(key, set())
        if homes and homes <= synced_src_docs:
            enrichment.append(key)
        else:
            ghosts.append(key)
    return sorted(ghosts), sorted(enrichment)


def reconcile(
    store: ox.Store,
    project_root: Path,
    config: KGConfig,
) -> ReconcileReport:
    """Run per-doc_type drift detection.

    Active doc_types come from `config.kg_active_doc_types`. The legacy
    `_load_doc_type_map` resolves each doc_type to a `docs/<subdir>`
    path; `scan_business_docs` enforces the same parser as the import
    codemod, so the comparison is apples-to-apples.
    """
    project_root = Path(project_root)
    type_map = _load_doc_type_map(str(project_root))
    active = sorted(config.kg_active_doc_types)
    authority = definition_authority(project_root)
    registry = build_prefix_registry(custom_entity_prefixes(project_root))

    # The symmetric diff only spans Document-backed content. Orphan entities
    # (authored without a Document, e.g. via `context write`) export as
    # per-entity cards whose Markdown form — link-style `[F-001](…)` instead of
    # strict xref, render-only `## Implements` sections — cannot round-trip back
    # through the ingest scanner, so re-scanning them yields phantom divergence.
    # The FS side drops card files (below); the KG side is restricted to
    # source_docs that own a `cf:Document` node. A no-op when every doc is
    # Document-backed; orphan cards drift-triage by their own content hash.
    covered_source_docs = _covered_source_docs(store, cf_namespace(config))

    triage = _hash_triage(store, project_root, config)
    synced_src_docs = {t.source_doc for t in triage if t.synced and t.source_doc}

    report = ReconcileReport(
        timestamp=_utc_now_iso(),
        active_doc_types=active,
        mode=context_mode(project_root),
    )

    # Pre-pass: scan every active doc_type once, recording the doc_id(s) that
    # *define* each entity and collecting every FS relation. A relation is a
    # project-global fact; the KG keys it by its subject's `cf:source_doc`
    # (`_kg_relations_with_homes`), so attributing the FS side by the doc that
    # merely *declares* the xref (arch declaring a Feature→Feature dependency)
    # would diverge. Bucketing FS relations by the subject's home doc keeps both
    # sides apples-to-apples.
    parsed_by_type: dict[str, list[Any]] = {}
    doc_ids_by_type: dict[str, set[str]] = {}
    entity_home: dict[str, set[str]] = {}
    raw_relations: list[tuple[RelKey, str]] = []  # (relation key, extraction doc_id)
    for doc_type in active:
        # Resolve the on-disk subdir; honour the framework.json override
        # the same way the legacy loader does.
        subdir = type_map.get(doc_type, doc_type)
        directory = project_root / "docs" / subdir
        parsed = scan_business_docs(project_root, [doc_type]) if directory.is_dir() else []
        # Drop per-entity card files; only Document-backed whole docs are
        # authoritative source for the diff (cards can't round-trip).
        parsed = [d for d in parsed if not _is_entity_card(d)]
        parsed_by_type[doc_type] = parsed
        doc_ids: set[str] = set()
        for doc in parsed:
            doc_ids.add(doc.doc_id)
            for entity in extract_entities(doc, authority=authority, registry=registry):
                entity_home.setdefault(entity.entity_id, set()).add(doc.doc_id)
            for relation in extract_relations(doc, registry):
                key = (
                    relation.subject_entity_id,
                    relation.predicate_curie,
                    relation.object_entity_id,
                )
                raw_relations.append((key, doc.doc_id))
        # If no parsed docs but the doc_type has a built-in subdir name, still
        # consult KG by the subdir-as-doc_id (cheap; usually empty).
        doc_ids_by_type[doc_type] = doc_ids or {subdir, doc_type}

    # Attribute each FS relation to the doc(s) the KG keys it under — its
    # subject node's `cf:source_doc`. A subordinate subject (AcceptanceCriteria)
    # is parent-local and defined in its extraction doc, so the edge lives there;
    # any other subject is keyed by its unique defining doc, which may differ
    # from the doc that merely declares the xref. A subject with no definition
    # resolves to no home and drops out — matching the KG, which never wrote an
    # edge for a subjectless node.
    fs_rel_by_doc: dict[str, set[RelKey]] = {}
    for key, ext_doc in raw_relations:
        homes = {ext_doc} if _is_subordinate_id(key[0]) else entity_home.get(key[0], set())
        for home in homes:
            fs_rel_by_doc.setdefault(home, set()).add(key)

    for doc_type in active:
        per = PerDocTypeReport(doc_type=doc_type)
        report.per_doc_type[doc_type] = per
        parsed = parsed_by_type[doc_type]
        doc_ids = doc_ids_by_type[doc_type]

        fs_entities: set[str] = set()
        fs_sections: set[str] = set()
        for doc in parsed:
            doc_entities = extract_entities(doc, authority=authority, registry=registry)
            for entity in doc_entities:
                fs_entities.add(entity.scope_key)
            _document, doc_sections = extract_structure(doc, doc_entities)
            for section in doc_sections:
                fs_sections.add(section.anchor)

        fs_relations: set[RelKey] = set()
        for did in doc_ids:
            fs_relations |= fs_rel_by_doc.get(did, set())

        # The KG side spans only Document-backed source_docs: orphan entities
        # (exported as cards, excluded from the FS side above) are out of scope
        # for the symmetric diff. On an empty graph (initial ingest / repair)
        # covered is empty, so the KG side is empty and FS-only entities still
        # surface as missing to drive reingest.
        kg_doc_ids = doc_ids & covered_source_docs

        kg_entities = _kg_entities_for_doc_ids(store, config, kg_doc_ids)
        kg_rel_homes = _kg_relations_with_homes(store, config, kg_doc_ids)
        kg_relations = set(kg_rel_homes)
        kg_sections = _kg_sections_for_doc_ids(store, config, kg_doc_ids)

        per.orphan_relations = sorted(_kg_orphan_relations_for_doc_ids(store, config, kg_doc_ids))
        per.missing_entities = sorted(fs_entities - kg_entities)
        per.ghost_entities = sorted(kg_entities - fs_entities)
        per.missing_relations = sorted(fs_relations - kg_relations)
        per.ghost_relations, per.enrichment_relations = _split_ghost_relations(
            kg_relations - fs_relations, kg_rel_homes, synced_src_docs
        )
        per.missing_sections = sorted(fs_sections - kg_sections)
        per.ghost_sections = sorted(kg_sections - fs_sections)

    # Remediation direction needs the symmetric diff: a never-exported
    # document whose doc_type shows the Markdown ahead of the graph
    # (missing > ghost) must ingest, not export.
    policy = ModePolicy.for_project(project_root)
    md_ahead_types = {
        doc_type
        for doc_type, per in report.per_doc_type.items()
        if per.missing_count > per.ghost_count
    }
    for t in triage:
        desynced = desynced_tile_sections(store, config, t.doc_iri)
        remediation = policy.remediation_for(t.state, md_ahead=t.doc_type in md_ahead_types)
        if desynced and remediation == REMEDIATE_NONE:
            remediation = REMEDIATE_MANUAL
        report.documents.append(
            DocumentDriftRecord(
                source_path=t.source_path,
                doc_id=t.doc_iri,
                state=t.state,
                remediation=remediation,
                desynced_sections=desynced,
            )
        )

    return report


def write_report(report: ReconcileReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


__all__ = [
    "DocumentDriftRecord",
    "PerDocTypeReport",
    "ReconcileReport",
    "RelKey",
    "reconcile",
    "write_report",
]
