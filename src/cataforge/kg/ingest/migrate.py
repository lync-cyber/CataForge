"""Six-phase migration orchestrator."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cataforge.kg._config import BUSINESS_DOC_TYPES as DEFAULT_DOC_TYPES
from cataforge.kg._config import KGConfig
from cataforge.kg.ingest.entity_extract import (
    ExtractedEntity,
    extract_entities,
)
from cataforge.kg.ingest.relation_extract import (
    ExtractedRelation,
    extract_relations,
)
from cataforge.kg.ingest.scan import scan_business_docs
from cataforge.kg.ingest.verify import VerifyResult, verify_after_write
from cataforge.kg.ingest.writer import (
    WriteStats,
    write_entities,
    write_project,
    write_relations,
)

if TYPE_CHECKING:
    import pyoxigraph as ox


@dataclass
class MigrationStats:
    parsed_docs: int = 0
    extracted_entities: int = 0
    extracted_relations: int = 0
    write_stats: WriteStats = field(default_factory=WriteStats)
    verify_result: VerifyResult | None = None
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "parsed_docs": self.parsed_docs,
            "extracted_entities": self.extracted_entities,
            "extracted_relations": self.extracted_relations,
            "entities_written": self.write_stats.entities_written,
            "entities_skipped": self.write_stats.entities_skipped,
            "relations_written": self.write_stats.relations_written,
            "relations_skipped": self.write_stats.relations_skipped,
            "dry_run": self.dry_run,
            "verify_ok": None if self.verify_result is None else self.verify_result.ok,
            "verify_missing": (
                [] if self.verify_result is None else list(self.verify_result.missing_entities)
            ),
            "verify_hash_mismatches": (
                []
                if self.verify_result is None
                else list(self.verify_result.content_hash_mismatches)
            ),
        }


def _read_project_metadata(project_root: Path) -> dict[str, str]:
    """Read `kg.project_id` / `kg.title` / `kg.process_model` from framework.json.

    Defaults: project_id=`proj-default`, title=`(unnamed)`, process_model=`waterfall`.
    Fixture projects ship a fully populated `kg` block.
    """
    framework_json = project_root / ".cataforge" / "framework.json"
    out = {"project_id": "proj-default", "title": "(unnamed)", "process_model": "waterfall"}
    if not framework_json.is_file():
        return out
    try:
        data = json.loads(framework_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return out
    kg = (data or {}).get("kg")
    if isinstance(kg, dict):
        for key in out:
            value = kg.get(key)
            if isinstance(value, str) and value:
                out[key] = value
    return out


def run_migration(
    store: ox.Store,
    project_root: Path,
    config: KGConfig,
    *,
    doc_types: tuple[str, ...] = DEFAULT_DOC_TYPES,
    dry_run: bool = False,
) -> tuple[MigrationStats, list[ExtractedEntity], list[ExtractedRelation]]:
    """Run phases 1–6 on `project_root` and return statistics.

    Dry-run mode runs phases 1–4 (the extraction half) and 6 against the
    pre-existing graph state, so reviewers see what would be written
    without committing anything. Phase 5 (write) is skipped.
    """
    stats = MigrationStats(dry_run=dry_run)

    # PHASE 1+2: SCAN + PARSE
    parsed_docs = scan_business_docs(project_root, list(doc_types))
    stats.parsed_docs = len(parsed_docs)

    # PHASE 3: ENTITY EXTRACT (per-doc), then cross-doc dedupe by entity_id.
    # First occurrence wins — `doc_types` ordering puts the document that
    # *defines* an entity (prd for Feature / AC, arch for Module, …) ahead
    # of documents that merely reference it.
    deduped_entities: dict[str, ExtractedEntity] = {}
    for doc in parsed_docs:
        for entity in extract_entities(doc):
            deduped_entities.setdefault(entity.entity_id, entity)
    entities: list[ExtractedEntity] = list(deduped_entities.values())
    stats.extracted_entities = len(entities)

    # PHASE 4: RELATION EXTRACT, dedupe by (s, p, o).
    deduped_relations: dict[tuple[str, str, str], ExtractedRelation] = {}
    for doc in parsed_docs:
        for relation in extract_relations(doc):
            key = (
                relation.subject_entity_id,
                relation.predicate_curie,
                relation.object_entity_id,
            )
            deduped_relations.setdefault(key, relation)
    relations: list[ExtractedRelation] = list(deduped_relations.values())
    stats.extracted_relations = len(relations)

    if dry_run:
        # Even in dry-run, surface what's missing from the existing graph
        # so reviewers can see drift between source and store.
        stats.verify_result = verify_after_write(store, entities, relations, config)
        return stats, entities, relations

    # PHASE 5: WRITE (Project node first, then entities, then relations).
    meta = _read_project_metadata(project_root)
    stats.write_stats = _write_phase5(store, meta, entities, relations, config)

    # PHASE 6: VERIFY
    stats.verify_result = verify_after_write(store, entities, relations, config)

    return stats, entities, relations


def _write_phase5(
    store: ox.Store,
    meta: dict[str, str],
    entities: list[ExtractedEntity],
    relations: list[ExtractedRelation],
    config: KGConfig,
) -> WriteStats:
    """Write project, entities, relations with compensating rollback on failure."""
    import pyoxigraph as ox  # noqa: PLC0415

    project_iri = write_project(
        store,
        meta["project_id"],
        meta["title"],
        meta["process_model"],
        config,
    )
    project_node = ox.NamedNode(project_iri)
    prior_project_quads = list(store.quads_for_pattern(project_node, None, None, None))

    write_stats: WriteStats | None = None
    rel_stats: WriteStats | None = None
    try:
        write_stats = write_entities(store, entities, project_iri, config)
        rel_stats = write_relations(store, relations, config)
    except Exception:
        _rollback_phase5(
            store,
            project_iri,
            prior_project_quads,
            write_stats.written_iris if write_stats is not None else [],
            rel_stats.written_relation_quads if rel_stats is not None else [],
            config,
        )
        raise

    combined = WriteStats(
        entities_written=write_stats.entities_written,
        entities_skipped=write_stats.entities_skipped,
        relations_written=rel_stats.relations_written,
        relations_skipped=rel_stats.relations_skipped,
        written_iris=write_stats.written_iris,
    )
    return combined


def _rollback_phase5(
    store: ox.Store,
    project_iri: str,
    prior_project_quads: list,
    written_entity_iris: list[str],
    written_relation_quads: list,
    config: KGConfig,
) -> None:
    """Best-effort compensating rollback for Phase 5 partial writes."""
    import pyoxigraph as ox  # noqa: PLC0415

    from cataforge.kg._quads import quads_for_subject as _quads_for_subject

    for iri in written_entity_iris:
        for q in _quads_for_subject(store, iri):
            with contextlib.suppress(Exception):
                store.remove(q)

    for q in written_relation_quads:
        with contextlib.suppress(Exception):
            store.remove(q)

    project_node = ox.NamedNode(project_iri)
    for q in list(store.quads_for_pattern(project_node, None, None, None)):
        with contextlib.suppress(Exception):
            store.remove(q)
    for q in prior_project_quads:
        with contextlib.suppress(Exception):
            store.add(q)
