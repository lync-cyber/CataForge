"""Phase 3b: derive document-structure nodes from a parsed doc + its entities.

Whereas `entity_extract` produces business entities (`F-001`, …), this
phase produces the structural backbone — one `Document` per file and one
`Section` per entity-owning heading — plus the containment edges that
make whole-document content first-class in the graph.

Scope: a Section is emitted for every `§`-level heading (level ≥ 2),
including pure-prose sections that own no entity, so whole-section reads
resolve from the graph. The Section carries the heading's prose body
(`narrative_body`) and `contains_entity` edges to the entities whose
innermost owning heading is this section; the Document links the sections
via `has_section`. The level-1 document title is represented by the
Document node itself; split-Volume nodes are out of scope for this phase.
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
    """Return the section's lines with trailing blank lines trimmed.

    Mirrors the legacy file slice (`loader._extract_section_from_lines`)
    so a KG-served whole-section read matches the file-served one.
    """
    lines = doc.raw.splitlines()[line_start:line_end]
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def extract_structure(
    doc: ParsedDoc,
    entities: list[ExtractedEntity],
) -> tuple[ExtractedDocument, list[ExtractedSection]]:
    """Return the Document node and one Section per `§`-level heading.

    `entities` are this document's own entities (the per-doc output of
    `extract_entities`); each is attached to its innermost owning heading
    via `contains_entity` (matched on `source_section` == heading title).
    """
    # Entities keyed by the title of their innermost owning heading.
    owned: dict[str, list[str]] = {}
    for entity in entities:
        owned.setdefault(entity.source_section, []).append(entity.entity_id)

    sections: list[ExtractedSection] = []
    seen_anchors: set[str] = set()
    for span in doc.sections:
        if span.level < 2:
            continue  # level-1 title is the Document node, not a Section
        anchor = span.title.strip()
        if not anchor or anchor in seen_anchors:
            continue
        seen_anchors.add(anchor)
        body = _section_body(doc, span.line_start, span.line_end)
        sections.append(
            ExtractedSection(
                doc_id=doc.doc_id,
                anchor=anchor,
                title=anchor,
                narrative_body=body,
                content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
                source_doc=doc.doc_id,
                contained_entity_ids=sorted(owned.get(anchor, [])),
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
