"""Extract TechStack entities from arch document §1.4 or tech-stack headings.

Arch documents contain a free-prose tech-stack section (typically §1.4)
that is not tagged with a TS-NNN entity_id.  This extractor identifies
the section by heading pattern, synthesises a slug-form entity_id
(``tech-stack-{doc_id}``), and populates the ``narrative_body`` /
``stack_layers`` extra slots defined in core.yaml.
"""
from __future__ import annotations

import hashlib
import re

from cataforge.kg.ingest.entity_extract import ExtractedEntity
from cataforge.kg.ingest.scan import HeadingSpan, ParsedDoc

_TECHSTACK_HEADING_RE = re.compile(
    r"§1\.4|tech[\s-]?stack|技术栈|technology\s+stack",
    re.IGNORECASE,
)

_LAYER_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+)", re.MULTILINE)


def _section_body(doc: ParsedDoc, span: HeadingSpan) -> str:
    lines = doc.raw.splitlines()
    return "\n".join(lines[span.line_start:span.line_end])


def _parse_layers(body: str) -> list[str]:
    """Extract top-level bullet items as stack layer labels."""
    return [m.group(1).strip() for m in _LAYER_BULLET_RE.finditer(body)]


def _make_entity_id(doc_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", doc_id.lower()).strip("-")
    return f"tech-stack-{slug}" if slug else "tech-stack"


def extract_techstack(doc: ParsedDoc) -> ExtractedEntity | None:
    """Return a TechStack entity if the doc contains a matching section."""
    if doc.doc_type != "arch":
        return None

    match_span: HeadingSpan | None = None
    for span in doc.sections:
        if _TECHSTACK_HEADING_RE.search(span.title):
            match_span = span
            break

    if match_span is None:
        return None

    body = _section_body(doc, match_span)
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    entity_id = _make_entity_id(doc.doc_id)
    layers = _parse_layers(body)

    extra_slots: dict[str, str | list[str]] = {
        "cf:narrative_body": body,
    }
    if layers:
        extra_slots["cf:stack_layers"] = layers

    return ExtractedEntity(
        entity_id=entity_id,
        class_name="TechStack",
        source_doc=doc.doc_id,
        source_section=match_span.title,
        content_hash=content_hash,
        section_line_start=match_span.line_start,
        section_line_end=match_span.line_end,
        file_path=doc.file_path,
        mtime=doc.mtime,
        extra_slots=extra_slots,
    )
