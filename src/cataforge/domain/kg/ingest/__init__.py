"""Markdown → KG ingest pipeline.

Implements the six-phase migration codemod:

    scan → parse → entity-extract → relation-extract → write → verify

The pipeline is intentionally split across modules so each phase is
unit-testable in isolation. `migrate.run_migration()` orchestrates the
six in order.
"""

from __future__ import annotations

from cataforge.domain.kg._config import BUSINESS_DOC_TYPES as DEFAULT_DOC_TYPES
from cataforge.domain.kg.ingest.entity_extract import (
    ENTITY_PREFIX_RE,
    ExtractedEntity,
    extract_entities,
)
from cataforge.domain.kg.ingest.frontmatter import parse_frontmatter
from cataforge.domain.kg.ingest.iri import (
    ENTITY_PREFIX_TO_CLASS,
    class_iri,
    document_iri,
    entity_iri,
    section_iri,
)
from cataforge.domain.kg.ingest.migrate import MigrationStats, run_migration
from cataforge.domain.kg.ingest.relation_extract import (
    ExtractedRelation,
    extract_relations,
)
from cataforge.domain.kg.ingest.scan import ParsedDoc, parse_doc_text, scan_business_docs
from cataforge.domain.kg.ingest.structure_extract import (
    ExtractedDocument,
    ExtractedSection,
    extract_structure,
)
from cataforge.domain.kg.ingest.verify import VerifyResult, verify_after_write
from cataforge.domain.kg.ingest.writer import write_entities, write_relations, write_structure

__all__ = [
    "DEFAULT_DOC_TYPES",
    "ENTITY_PREFIX_RE",
    "ENTITY_PREFIX_TO_CLASS",
    "ExtractedDocument",
    "ExtractedEntity",
    "ExtractedRelation",
    "ExtractedSection",
    "MigrationStats",
    "ParsedDoc",
    "VerifyResult",
    "class_iri",
    "document_iri",
    "entity_iri",
    "extract_entities",
    "extract_relations",
    "extract_structure",
    "parse_doc_text",
    "parse_frontmatter",
    "run_migration",
    "scan_business_docs",
    "section_iri",
    "verify_after_write",
    "write_entities",
    "write_relations",
    "write_structure",
]
