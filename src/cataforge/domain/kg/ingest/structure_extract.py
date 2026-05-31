"""Phase 3b: derive document-structure nodes from a parsed doc + its entities.

Whereas `entity_extract` produces business entities (`F-001`, …), this
phase produces the structural backbone — one `Document` per file and one
`Section` per entity-owning heading — plus the containment edges that
make whole-document content first-class in the graph.

Scope: a Section is emitted for every heading that owns at least one
entity. The Section carries the heading's prose body (`narrative_body`)
and `contains_entity` edges to the entities sourced from it; the Document
links the sections via `has_section`. Pure-prose sections (no entities)
and split-Volume nodes are out of scope for this phase.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from cataforge.domain.kg.ingest.entity_extract import ExtractedEntity
from cataforge.domain.kg.ingest.scan import ParsedDoc


@dataclass
class ExtractedSection:
    """One entity-owning heading captured as a structural node."""

    doc_id: str
    anchor: str  # the heading title, used as the stable section anchor
    title: str
    narrative_body: str
    content_hash: str
    source_doc: str
    contained_entity_ids: list[str] = field(default_factory=list)


@dataclass
class ExtractedDocument:
    """One business-doc Markdown file captured as a structural node."""

    doc_id: str
    doc_type: str
    title: str
    source_doc: str
    content_hash: str
    section_anchors: list[str] = field(default_factory=list)
    version: str | None = None
    status: str | None = None


def _section_body(doc: ParsedDoc, line_start: int, line_end: int) -> str:
    return "\n".join(doc.raw.splitlines()[line_start:line_end])


def extract_structure(
    doc: ParsedDoc,
    entities: list[ExtractedEntity],
) -> tuple[ExtractedDocument, list[ExtractedSection]]:
    """Return the Document node and its entity-owning Section nodes.

    `entities` are this document's own entities (the per-doc output of
    `extract_entities`), so `source_section` / `section_line_*` are
    attributed to headings in this file.
    """
    # Group entities by the heading that owns them. `source_section` is
    # the heading title; entities under the same heading share line bounds.
    groups: dict[str, list[ExtractedEntity]] = {}
    for entity in entities:
        groups.setdefault(entity.source_section, []).append(entity)

    sections: list[ExtractedSection] = []
    for anchor, group in groups.items():
        head = group[0]
        body = _section_body(doc, head.section_line_start, head.section_line_end)
        sections.append(
            ExtractedSection(
                doc_id=doc.doc_id,
                anchor=anchor,
                title=anchor,
                narrative_body=body,
                content_hash=head.content_hash,
                source_doc=doc.doc_id,
                contained_entity_ids=sorted(e.entity_id for e in group),
            )
        )
    sections.sort(key=lambda s: s.anchor)

    fm = doc.frontmatter or {}
    title = fm.get("title")
    if not isinstance(title, str) or not title:
        title = doc.doc_id
    version = fm.get("version") if isinstance(fm.get("version"), str) else None
    status = fm.get("status") if isinstance(fm.get("status"), str) else None

    document = ExtractedDocument(
        doc_id=doc.doc_id,
        doc_type=doc.doc_type,
        title=title,
        source_doc=doc.doc_id,
        content_hash=hashlib.sha256(doc.raw.encode("utf-8")).hexdigest(),
        section_anchors=[s.anchor for s in sections],
        version=version,
        status=status,
    )
    return document, sections
