"""Auto-fix KG drift detected by reconcile."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._quads import _slot_iri, quads_for_subject
from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _term_value,
    cf_namespace,
    escape_sparql_literal,
)
from cataforge.domain.kg.ingest.entity_extract import extract_entities
from cataforge.domain.kg.ingest.iri import entity_iri, subordinate_entity_iri
from cataforge.domain.kg.ingest.migrate import _read_project_metadata
from cataforge.domain.kg.ingest.relation_extract import extract_relations
from cataforge.domain.kg.ingest.scan import scan_business_docs
from cataforge.domain.kg.ingest.writer import write_entities, write_project, write_relations
from cataforge.domain.kg.reconcile import reconcile

if TYPE_CHECKING:
    import pyoxigraph as ox


@dataclass
class RepairStats:
    ghosts_removed: int = 0
    missing_ingested: int = 0
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


def _entity_quads_by_scope_key(store: ox.Store, scope_key: str, config: KGConfig) -> list:
    return quads_for_subject(store, _scope_key_to_iri(scope_key, config))


def _ghost_relation_quads(
    store: ox.Store,
    subject_id: str,
    predicate_curie: str,
    object_id: str,
    config: KGConfig,
) -> list:
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
    quads: list = []
    for row in store.query(sparql):
        s_node = _term_value(_row_lookup(row, "s"))
        o_node = _term_value(_row_lookup(row, "o"))
        if s_node is not None and o_node is not None:
            quads.append(ox.Quad(ox.NamedNode(str(s_node)), pred_node, ox.NamedNode(str(o_node))))
    return quads


def _reingest_doc_type(
    store: ox.Store,
    project_root: Path,
    doc_type: str,
    config: KGConfig,
) -> int:
    """Re-run the ingest pipeline for a single doc_type. Returns entities written."""
    parsed = scan_business_docs(project_root, [doc_type])
    if not parsed:
        return 0

    meta = _read_project_metadata(project_root)
    project_iri = write_project(
        store, meta["project_id"], meta["title"], meta["process_model"], config
    )

    total = 0
    for doc in parsed:
        entities = extract_entities(doc)
        relations = extract_relations(doc)
        ws = write_entities(store, entities, project_iri, config)
        write_relations(store, relations, config)
        total += ws.entities_written
    return total


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
    if report.ok:
        return RepairStats()

    stats = RepairStats()

    for per in report.per_doc_type.values():
        ghost_entity_snapshots: dict[str, list] = {}
        ghost_relation_snapshots: list = []

        for scope_key in per.ghost_entities:
            if not dry_run:
                try:
                    snapshot = _entity_quads_by_scope_key(store, scope_key, config)
                    ghost_entity_snapshots[scope_key] = list(snapshot)
                    for q in snapshot:
                        store.remove(q)
                except Exception as exc:  # noqa: BLE001
                    stats.errors.append(f"ghost entity {scope_key}: {exc}")
                    continue
            stats.ghosts_removed += 1

        for s_id, pred, o_id in per.ghost_relations:
            if not dry_run:
                try:
                    edge_quads = _ghost_relation_quads(store, s_id, pred, o_id, config)
                    ghost_relation_snapshots.extend(edge_quads)
                    for q in edge_quads:
                        store.remove(q)
                except Exception as exc:  # noqa: BLE001
                    stats.errors.append(f"ghost relation ({s_id},{pred},{o_id}): {exc}")
                    continue
            stats.ghosts_removed += 1

        if per.missing_entities or per.missing_relations:
            if not dry_run:
                try:
                    written = _reingest_doc_type(store, project_root, per.doc_type, config)
                    stats.missing_ingested += written
                except Exception as exc:  # noqa: BLE001
                    stats.errors.append(f"reingest {per.doc_type}: {exc}")
                    stats.errors.extend(
                        _restore_ghosts(store, ghost_entity_snapshots, ghost_relation_snapshots)
                    )
                    stats.ghosts_removed -= len(ghost_entity_snapshots) + len(
                        ghost_relation_snapshots
                    )
            else:
                stats.missing_ingested += len(per.missing_entities) + len(per.missing_relations)

    return stats


def _restore_ghosts(
    store: ox.Store,
    entity_snapshots: dict[str, list],
    relation_snapshots: list,
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
    return errors


__all__ = [
    "RepairStats",
    "repair",
]
