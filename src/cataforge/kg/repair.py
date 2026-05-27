"""Auto-fix KG drift detected by reconcile."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from cataforge.kg._config import KGConfig
from cataforge.kg._quads import quads_for_subject
from cataforge.kg.ingest.entity_extract import extract_entities
from cataforge.kg.ingest.iri import entity_iri
from cataforge.kg.ingest.relation_extract import extract_relations
from cataforge.kg.ingest.scan import scan_business_docs
from cataforge.kg.ingest.writer import write_entities, write_project, write_relations
from cataforge.kg.reconcile import reconcile

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
    from cataforge.kg._quads import build_relation_quad  # noqa: PLC0415

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

    project_iri = write_project(
        store, "proj-default", str(project_root.name), "waterfall", config
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
    """Two-phase repair: remove ghosts, then ingest missing items."""
    report = reconcile(store, project_root, config)
    if report.ok:
        return RepairStats()

    stats = RepairStats()

    for per in report.per_doc_type.values():
        for eid in per.ghost_entities:
            if not dry_run:
                try:
                    _remove_entity_quads(store, eid, config)
                except Exception as exc:  # noqa: BLE001
                    stats.errors.append(f"ghost entity {eid}: {exc}")
                    continue
            stats.ghosts_removed += 1

        for s_id, pred, o_id in per.ghost_relations:
            if not dry_run:
                try:
                    _remove_relation_quad(store, s_id, pred, o_id, config)
                except Exception as exc:  # noqa: BLE001
                    stats.errors.append(f"ghost relation ({s_id},{pred},{o_id}): {exc}")
                    continue
            stats.ghosts_removed += 1

        if per.missing_entities or per.missing_relations:
            if not dry_run:
                try:
                    written = _reingest_doc_type(
                        store, project_root, per.doc_type, config
                    )
                    stats.missing_ingested += written
                except Exception as exc:  # noqa: BLE001
                    stats.errors.append(f"reingest {per.doc_type}: {exc}")
            else:
                stats.missing_ingested += (
                    len(per.missing_entities) + len(per.missing_relations)
                )

    return stats


__all__ = [
    "RepairStats",
    "repair",
]
