"""Markdown → KG ingest pipeline (task-7 §7.2).

Sub-PR 3 implements the six-phase migration codemod described in
`task-7-rollout-strategy.md §7.2`:

    scan → parse → entity-extract → relation-extract → write → verify

The pipeline is intentionally split across modules so each phase is
unit-testable in isolation. `migrate.run_migration()` orchestrates the
six in order.
"""
from __future__ import annotations

from cataforge.kg.ingest.entity_extract import (
    ENTITY_PREFIX_RE,
    ExtractedEntity,
    extract_entities,
)
from cataforge.kg.ingest.frontmatter import parse_frontmatter
from cataforge.kg.ingest.iri import (
    ENTITY_PREFIX_TO_CLASS,
    class_iri,
    entity_iri,
    id_prefix_to_type,
)
from cataforge.kg.ingest.migrate import DEFAULT_DOC_TYPES, MigrationStats, run_migration
from cataforge.kg.ingest.relation_extract import (
    ExtractedRelation,
    extract_relations,
    infer_predicate,
)
from cataforge.kg.ingest.scan import ParsedDoc, scan_business_docs
from cataforge.kg.ingest.verify import VerifyResult, verify_after_write
from cataforge.kg.ingest.writer import write_entities, write_relations

__all__ = [
    "DEFAULT_DOC_TYPES",
    "ENTITY_PREFIX_RE",
    "ENTITY_PREFIX_TO_CLASS",
    "ExtractedEntity",
    "ExtractedRelation",
    "MigrationStats",
    "ParsedDoc",
    "VerifyResult",
    "class_iri",
    "entity_iri",
    "extract_entities",
    "extract_relations",
    "id_prefix_to_type",
    "infer_predicate",
    "parse_frontmatter",
    "run_migration",
    "scan_business_docs",
    "verify_after_write",
    "write_entities",
    "write_relations",
]
