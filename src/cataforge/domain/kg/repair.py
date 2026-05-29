"""Auto-fix KG drift detected by reconcile."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._quads import quads_for_subject
from cataforge.domain.kg.ingest.entity_extract import extract_entities
from cataforge.domain.kg.ingest.iri import entity_iri
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


def _remove_entity_quads(store: ox.Store, eid: str, config: KGConfig) -> None:
    iri = entity_iri(eid, config.base_namespace)
    for q in quads_for_subject(store, iri):
        store.remove(q)


def _remove_relation_quad(
    store: ox.Store,
    subject_id: str,
    predicate_curie: str,
    object_id: str,
    config: KGConfig,
) -> None:
    from cataforge.domain.kg._quads import build_relation_quad  # noqa: PLC0415

    quad = build_relation_quad(subject_id, predicate_curie, object_id, config)
    store.remove(quad)


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

        for eid in per.ghost_entities:
            if not dry_run:
                iri = entity_iri(eid, config.base_namespace)
                try:
                    snapshot = quads_for_subject(store, iri)
                    ghost_entity_snapshots[eid] = list(snapshot)
                    _remove_entity_quads(store, eid, config)
                except Exception as exc:  # noqa: BLE001
                    stats.errors.append(f"ghost entity {eid}: {exc}")
                    continue
            stats.ghosts_removed += 1

        for s_id, pred, o_id in per.ghost_relations:
            if not dry_run:
                try:
                    from cataforge.domain.kg._quads import build_relation_quad  # noqa: PLC0415

                    snapshot_quad = build_relation_quad(s_id, pred, o_id, config)
                    ghost_relation_snapshots.append(snapshot_quad)
                    _remove_relation_quad(store, s_id, pred, o_id, config)
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
                    _restore_ghosts(store, ghost_entity_snapshots, ghost_relation_snapshots)
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
) -> None:
    """Restore ghost quads after a failed reingest (best-effort)."""
    for quads in entity_snapshots.values():
        for q in quads:
            with contextlib.suppress(Exception):
                store.add(q)
    for q in relation_snapshots:
        with contextlib.suppress(Exception):
            store.add(q)


__all__ = [
    "RepairStats",
    "repair",
]
