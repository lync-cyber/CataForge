"""Auto-fix KG drift detected by reconcile."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cataforge.domain.docs.index_ops import _load_doc_type_map
from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._dispatch import custom_entity_prefixes, definition_authority
from cataforge.domain.kg._errors import KGDocumentCollisionError
from cataforge.domain.kg._quads import (
    _slot_iri,
    attribute_subject_quads,
    quads_for_subject,
    quads_targeting,
)
from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _term_value,
    cf_namespace,
    escape_sparql_literal,
    select_rows,
)
from cataforge.domain.kg.document_guard import ensure_document_replaceable
from cataforge.domain.kg.ingest.entity_extract import build_prefix_registry, extract_entities
from cataforge.domain.kg.ingest.iri import entity_iri, subordinate_entity_iri
from cataforge.domain.kg.ingest.migrate import _read_project_metadata
from cataforge.domain.kg.ingest.relation_extract import extract_relations
from cataforge.domain.kg.ingest.scan import format_doc_id_collisions, scan_business_docs
from cataforge.domain.kg.ingest.structure_extract import extract_structure
from cataforge.domain.kg.ingest.writer import (
    revert_home_synced,
    write_entities,
    write_project,
    write_relations,
    write_structure,
)
from cataforge.domain.kg.reconcile import reconcile

if TYPE_CHECKING:
    import pyoxigraph as ox

    from cataforge.domain.kg.reconcile import PerDocTypeReport


@dataclass
class RepairStats:
    ghosts_removed: int = 0
    missing_ingested: int = 0
    ghost_sections_removed: int = 0
    missing_sections_ingested: int = 0
    orphan_relations_removed: int = 0
    errors: list[str] = field(default_factory=list)


def _scope_key_to_iri(scope_key: str, config: KGConfig) -> str:
    """Map a reconcile scope key back to its node IRI.

    `parent/entity_id` → parent-scoped subordinate IRI; a bare `entity_id`
    → flat IRI. Entity ids never contain a slash, so the split is unambiguous.
    """
    base = config.base_namespace
    if "/" in scope_key:
        parent_id, entity_id = scope_key.split("/", 1)
        return subordinate_entity_iri(parent_id, entity_id, base)
    return entity_iri(scope_key, base)


def _entity_quads_by_scope_key(store: ox.Store, scope_key: str, config: KGConfig) -> list[Any]:
    iri = _scope_key_to_iri(scope_key, config)
    return quads_for_subject(store, iri) + attribute_subject_quads(store, iri, cf_namespace(config))


def _ghost_relation_quads(
    store: ox.Store,
    subject_id: str,
    predicate_curie: str,
    object_id: str,
    config: KGConfig,
) -> list[Any]:
    """Return the live edge quad(s) for a `(subject, predicate, object)` triple.

    Resolves endpoints by `cf:entity_id` rather than reconstructing flat IRIs,
    so an edge pointing at a parent-scoped subordinate node is still found.
    """
    import pyoxigraph as ox  # noqa: PLC0415

    ns = cf_namespace(config)
    pred_iri = _slot_iri(predicate_curie, ns)
    s_lit = escape_sparql_literal(subject_id)
    o_lit = escape_sparql_literal(object_id)
    sparql = (
        f"PREFIX cf: <{ns}> SELECT ?s ?o WHERE {{ "
        f'  ?s cf:entity_id "{s_lit}" . '
        f'  ?o cf:entity_id "{o_lit}" . '
        f"  ?s <{pred_iri}> ?o . "
        "}"
    )
    pred_node = ox.NamedNode(pred_iri)
    quads: list[Any] = []
    for row in select_rows(store, sparql):
        s_node = _term_value(_row_lookup(row, "s"))
        o_node = _term_value(_row_lookup(row, "o"))
        if s_node is not None and o_node is not None:
            quads.append(ox.Quad(ox.NamedNode(str(s_node)), pred_node, ox.NamedNode(str(o_node))))
    return quads


def _doc_ids_for_doc_type(project_root: Path, doc_type: str) -> set[str]:
    """Doc ids attributed to a doc_type — same derivation as reconcile."""
    type_map = _load_doc_type_map(str(project_root))
    subdir = type_map.get(doc_type, doc_type)
    directory = Path(project_root) / "docs" / subdir
    parsed = scan_business_docs(project_root, [doc_type]) if directory.is_dir() else []
    doc_ids = {doc.doc_id for doc in parsed}
    return doc_ids or {subdir, doc_type}


def _ghost_section_quads(
    store: ox.Store,
    anchor: str,
    doc_ids: set[str],
    config: KGConfig,
) -> list[Any]:
    """Live quads for the Section node(s) with `anchor` sourced from `doc_ids`.

    Returns the node's own quads plus incoming edges (the Document's
    `cf:has_section`), so removal leaves no dangling reference. Scoping by
    `cf:source_doc` keeps a same-anchor Section in another document intact.
    """
    ns = cf_namespace(config)
    values_clause = " ".join(f'"{escape_sparql_literal(d)}"' for d in sorted(doc_ids))
    anchor_lit = escape_sparql_literal(anchor)
    sparql = (
        f"PREFIX cf: <{ns}> "
        "SELECT DISTINCT ?s WHERE { "
        f"  VALUES ?src {{ {values_clause} }} "
        f'  ?s a cf:Section ; cf:section_anchor "{anchor_lit}" ; cf:source_doc ?src . '
        "}"
    )
    quads: list[Any] = []
    for row in select_rows(store, sparql):
        node = _term_value(_row_lookup(row, "s"))
        if node is None:
            continue
        iri = str(node)
        quads.extend(quads_for_subject(store, iri))
        quads.extend(quads_targeting(store, iri))
    return quads


def _reingest_doc_type(
    store: ox.Store,
    project_root: Path,
    doc_type: str,
    config: KGConfig,
    *,
    home_synced_out: list[tuple[list[Any], list[Any]]] | None = None,
) -> tuple[int, int]:
    """Re-run the ingest pipeline for a single doc_type.

    Returns ``(entities_written, sections_written)``. Applied hash-skip home
    syncs are appended to ``home_synced_out`` as they land, so the caller's
    failure branch can invert them even when a later write in the batch raises.
    """
    parsed = scan_business_docs(project_root, [doc_type])
    if not parsed:
        return 0, 0

    authority = definition_authority(project_root)
    registry = build_prefix_registry(custom_entity_prefixes(project_root))
    extracted = []
    for doc in parsed:
        entities = extract_entities(doc, authority=authority, registry=registry)
        relations = extract_relations(doc, registry)
        document, doc_sections = extract_structure(doc, entities)
        extracted.append((entities, relations, document, doc_sections))

    # Approved-content freeze: gate the whole doc_type before any write so a
    # refused re-ingest leaves zero mutation.
    for _entities, _relations, document, _sections in extracted:
        ensure_document_replaceable(store, config, document.doc_id, document.content_hash)

    meta = _read_project_metadata(project_root)
    project_iri = write_project(
        store, meta["project_id"], meta["title"], meta["process_model"], config
    )

    entities_total = 0
    sections_total = 0
    for entities, relations, document, doc_sections in extracted:
        ws = write_entities(store, entities, project_iri, config)
        if home_synced_out is not None:
            home_synced_out.extend(ws.home_synced)
        write_relations(store, relations, config)
        ss = write_structure(store, [document], doc_sections, config)
        entities_total += ws.entities_written
        sections_total += ss.sections_written
    return entities_total, sections_total


def repair(
    store: ox.Store,
    project_root: Path,
    config: KGConfig,
    *,
    dry_run: bool = False,
) -> RepairStats:
    """Two-phase repair: remove ghosts, then ingest missing items.

    Ghost quads are snapshotted before deletion. If the subsequent
    reingest phase fails for a doc_type, the ghost quads from that
    doc_type are restored so the store is not left in a half-mutated
    state.
    """
    report = reconcile(store, project_root, config)
    collisions = [c for per in report.per_doc_type.values() for c in per.doc_id_collisions]
    if collisions:
        # An ambiguous batch turns the whole KG side of the diff into phantom
        # ghosts; proceeding would delete healthy structure. Refuse before any
        # mutation — the author must resolve the file collision first.
        raise KGDocumentCollisionError(format_doc_id_collisions(collisions), collisions)
    if report.ok:
        return RepairStats()

    stats = RepairStats()

    for per in report.per_doc_type.values():
        entity_snaps = _remove_ghost_entities(store, per, config, stats, dry_run=dry_run)
        relation_snaps = _remove_ghost_relations(store, per, config, stats, dry_run=dry_run)
        _remove_orphan_relations(store, per, config, stats, dry_run=dry_run)
        section_snaps = _remove_ghost_sections(
            store, project_root, per, config, stats, dry_run=dry_run
        )
        _ingest_missing(
            store,
            project_root,
            per,
            config,
            stats,
            entity_snaps,
            relation_snaps,
            section_snaps,
            dry_run=dry_run,
        )

    return stats


def _remove_ghost_entities(
    store: ox.Store,
    per: PerDocTypeReport,
    config: KGConfig,
    stats: RepairStats,
    *,
    dry_run: bool,
) -> dict[str, list[Any]]:
    snapshots: dict[str, list[Any]] = {}
    for scope_key in per.ghost_entities:
        if not dry_run:
            try:
                snapshot = _entity_quads_by_scope_key(store, scope_key, config)
                snapshots[scope_key] = list(snapshot)
                for q in snapshot:
                    store.remove(q)
            except Exception as exc:  # noqa: BLE001
                stats.errors.append(f"ghost entity {scope_key}: {exc}")
                continue
        stats.ghosts_removed += 1
    return snapshots


def _remove_ghost_relations(
    store: ox.Store,
    per: PerDocTypeReport,
    config: KGConfig,
    stats: RepairStats,
    *,
    dry_run: bool,
) -> list[Any]:
    snapshots: list[Any] = []
    for s_id, pred, o_id in per.ghost_relations:
        if not dry_run:
            try:
                edge_quads = _ghost_relation_quads(store, s_id, pred, o_id, config)
                snapshots.extend(edge_quads)
                for q in edge_quads:
                    store.remove(q)
            except Exception as exc:  # noqa: BLE001
                stats.errors.append(f"ghost relation ({s_id},{pred},{o_id}): {exc}")
                continue
        stats.ghosts_removed += 1
    return snapshots


def _orphan_relation_quads(
    store: ox.Store,
    subject_id: str,
    predicate_curie: str,
    object_id: str,
    config: KGConfig,
) -> list[Any]:
    """Return the dangling edge quad(s) whose object resolves to no entity node.

    The subject is resolved by `cf:entity_id`; the object is reconstructed from
    its `entity_id` (or `parent/entity_id`) since a dangling target carries no
    `cf:entity_id` literal to match on.
    """
    import pyoxigraph as ox  # noqa: PLC0415

    ns = cf_namespace(config)
    pred_iri = _slot_iri(predicate_curie, ns)
    obj_iri = _scope_key_to_iri(object_id, config)
    s_lit = escape_sparql_literal(subject_id)
    sparql = (
        f"PREFIX cf: <{ns}> SELECT ?s WHERE {{ "
        f'  ?s cf:entity_id "{s_lit}" . '
        f"  ?s <{pred_iri}> <{obj_iri}> . "
        "}"
    )
    pred_node = ox.NamedNode(pred_iri)
    obj_node = ox.NamedNode(obj_iri)
    quads: list[Any] = []
    for row in select_rows(store, sparql):
        s_node = _term_value(_row_lookup(row, "s"))
        if s_node is not None:
            quads.append(ox.Quad(ox.NamedNode(str(s_node)), pred_node, obj_node))
    return quads


def _remove_orphan_relations(
    store: ox.Store,
    per: PerDocTypeReport,
    config: KGConfig,
    stats: RepairStats,
    *,
    dry_run: bool,
) -> None:
    """Prune traceability edges whose target entity no longer exists.

    A pure deletion with no reingest counterpart — the FS source no longer
    declares the edge (its target was renamed/deleted), so it is unconditionally
    stale and not threaded into the reingest rollback.
    """
    for s_id, pred, o_id in per.orphan_relations:
        if not dry_run:
            try:
                for q in _orphan_relation_quads(store, s_id, pred, o_id, config):
                    store.remove(q)
            except Exception as exc:  # noqa: BLE001
                stats.errors.append(f"orphan relation ({s_id},{pred},{o_id}): {exc}")
                continue
        stats.orphan_relations_removed += 1


def _remove_ghost_sections(
    store: ox.Store,
    project_root: Path,
    per: PerDocTypeReport,
    config: KGConfig,
    stats: RepairStats,
    *,
    dry_run: bool,
) -> dict[str, list[Any]]:
    snapshots: dict[str, list[Any]] = {}
    if not per.ghost_sections:
        return snapshots
    doc_ids = _doc_ids_for_doc_type(project_root, per.doc_type)
    for anchor in per.ghost_sections:
        if not dry_run:
            try:
                snapshot = _ghost_section_quads(store, anchor, doc_ids, config)
                snapshots[anchor] = list(snapshot)
                for q in snapshot:
                    store.remove(q)
            except Exception as exc:  # noqa: BLE001
                stats.errors.append(f"ghost section {anchor}: {exc}")
                continue
        stats.ghost_sections_removed += 1
    return snapshots


def _ingest_missing(
    store: ox.Store,
    project_root: Path,
    per: PerDocTypeReport,
    config: KGConfig,
    stats: RepairStats,
    entity_snapshots: dict[str, list[Any]],
    relation_snapshots: list[Any],
    section_snapshots: dict[str, list[Any]],
    *,
    dry_run: bool,
) -> None:
    """Reingest a doc_type's missing items; restore its ghosts on failure."""
    if not (per.missing_entities or per.missing_relations or per.missing_sections):
        return
    if dry_run:
        stats.missing_ingested += len(per.missing_entities) + len(per.missing_relations)
        stats.missing_sections_ingested += len(per.missing_sections)
        return
    home_synced: list[tuple[list[Any], list[Any]]] = []
    try:
        entities_written, sections_written = _reingest_doc_type(
            store, project_root, per.doc_type, config, home_synced_out=home_synced
        )
        stats.missing_ingested += entities_written
        stats.missing_sections_ingested += sections_written
    except Exception as exc:  # noqa: BLE001
        stats.errors.append(f"reingest {per.doc_type}: {exc}")
        revert_home_synced(store, home_synced)
        stats.errors.extend(
            _restore_ghosts(store, entity_snapshots, relation_snapshots, section_snapshots)
        )
        stats.ghosts_removed -= len(entity_snapshots) + len(relation_snapshots)
        stats.ghost_sections_removed -= len(section_snapshots)


def _restore_ghosts(
    store: ox.Store,
    entity_snapshots: dict[str, list[Any]],
    relation_snapshots: list[Any],
    section_snapshots: dict[str, list[Any]] | None = None,
) -> list[str]:
    """Restore ghost quads after a failed reingest (best-effort).

    Returns a description of every quad that could not be restored. A
    non-empty result means the store is in a mixed state and the caller
    should surface it rather than report a clean rollback.
    """
    errors: list[str] = []
    for eid, quads in entity_snapshots.items():
        for q in quads:
            try:
                store.add(q)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"restore ghost entity {eid}: {exc}")
    for q in relation_snapshots:
        try:
            store.add(q)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"restore ghost relation: {exc}")
    for anchor, quads in (section_snapshots or {}).items():
        for q in quads:
            try:
                store.add(q)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"restore ghost section {anchor}: {exc}")
    return errors


__all__ = [
    "RepairStats",
    "repair",
]
