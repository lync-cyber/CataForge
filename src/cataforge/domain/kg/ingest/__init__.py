"""Markdown → KG ingest pipeline.

Implements the six-phase migration codemod:

    scan → parse → entity-extract → relation-extract → write → verify

The pipeline is intentionally split across modules so each phase is
unit-testable in isolation. `migrate.run_migration()` orchestrates the
six in order.
"""
from __future__ import annotations

from cataforge.domain.kg.ingest.entity_extract import (
    ENTITY_PREFIX_RE,
    ExtractedEntity,
    extract_entities,
)
from cataforge.domain.kg.ingest.frontmatter import parse_frontmatter
from cataforge.domain.kg.ingest.iri import (
    ENTITY_PREFIX_TO_CLASS,
    class_iri,
    entity_iri,
)
from cataforge.domain.kg.ingest.migrate import DEFAULT_DOC_TYPES, MigrationStats, run_migration
from cataforge.domain.kg.ingest.relation_extract import (
    ExtractedRelation,
    extract_relations,
)
from cataforge.domain.kg.ingest.scan import ParsedDoc, scan_business_docs
from cataforge.domain.kg.ingest.verify import VerifyResult, verify_after_write
from cataforge.domain.kg.ingest.writer import write_entities, write_relations

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
    "parse_frontmatter",
    "run_migration",
    "scan_business_docs",
    "verify_after_write",
    "write_entities",
    "write_relations",
]
