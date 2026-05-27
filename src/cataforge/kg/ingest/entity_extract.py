"""Phase 3 of task-7 §7.2: extract business entities from parsed Markdown.

Each entity is uniquely identified by its `entity_id` (e.g. `F-001`).
The codemod records the first occurrence inside the first owning section
plus a SHA-256 content hash of that section's body — re-imports compare
the hash to detect content drift.

The patterns `ENTITY_PREFIX_RE` and `XREF_RE` live here so phase 3 can
exclude xref occurrences from entity detection without a circular
dependency with `relation_extract`.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cataforge.kg.ingest.iri import ENTITY_PREFIX_TO_CLASS
from cataforge.kg.ingest.scan import HeadingSpan, ParsedDoc

_LAYER_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+)", re.MULTILINE)

def _extract_techstack_slots(entity: ExtractedEntity, section_text: str) -> None:
    entity.extra_slots["cf:narrative_body"] = section_text
    layers = [m.group(1).strip() for m in _LAYER_BULLET_RE.finditer(section_text)]
    if layers:
        entity.extra_slots["cf:stack_layers"] = layers


_EXTRA_SLOT_EXTRACTORS: dict[str, Callable[[ExtractedEntity, str], None]] = {
    "TechStack": _extract_techstack_slots,
}

# Match entity-id occurrences inside arbitrary text. Longest-prefix-first
# ordering on the alternation guards against `API-001` matching as `A-001`
# under naïve `[A-Z]+`. We do this by sorting prefixes by descending length
# at module import time.
_PREFIX_ALT = "|".join(
    sorted((re.escape(p) for p in ENTITY_PREFIX_TO_CLASS), key=len, reverse=True)
)
ENTITY_PREFIX_RE = re.compile(rf"\b(?:{_PREFIX_ALT})-\d{{3,}}\b")

# Strict xref form: `doc_id#§<section>.<ENTITY-NNN>`. Shared with
# relation_extract; defined here to break the import cycle.
XREF_RE = re.compile(
    r"\b(?P<doc>[\w-]+)#§(?P<section>\d+(?:\.\d+)*)\.(?P<entity>[A-Z]+-\d{3,})\b"
)


@dataclass
class ExtractedEntity:
    """A single entity_id occurrence captured during phase 3."""

    entity_id: str
    class_name: str
    source_doc: str
    source_section: str
    content_hash: str
    section_line_start: int
    section_line_end: int
    file_path: Path
    mtime: float
    extra_slots: dict[str, Any] = field(default_factory=dict)


def _section_for_line(spans: list[HeadingSpan], line_idx: int) -> HeadingSpan | None:
    """Return the deepest heading whose span contains `line_idx`."""
    candidates = [s for s in spans if s.line_start <= line_idx < s.line_end]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.level)


def _line_index_for_offset(text: str, offset: int) -> int:
    """Return the 0-based line index of byte offset `offset` in `text`."""
    return text.count("\n", 0, offset)


def extract_entities(doc: ParsedDoc) -> list[ExtractedEntity]:
    """Phase 3: scan `doc` for entity_id occurrences.

    A given `entity_id` is emitted at most once per document — at the
    first match, owned by the innermost heading whose span contains it.
    Cross-document duplicates are resolved upstream by
    `migrate.dedupe_entities()` so the canonical definition wins (first
    document in doc_type scan order, typically prd for Feature / AC).

    Xref pattern matches (`prd#§2.F-001` inside an arch document) are
    excluded; otherwise the target entity_id leaks into every doc that
    references it.
    """
    xref_spans = [(m.start(), m.end()) for m in XREF_RE.finditer(doc.raw)]

    def _inside_xref(offset: int) -> bool:
        return any(start <= offset < end for start, end in xref_spans)

    seen: dict[str, ExtractedEntity] = {}
    for match in ENTITY_PREFIX_RE.finditer(doc.raw):
        if _inside_xref(match.start()):
            continue
        entity_id = match.group(0)
        if entity_id in seen:
            continue
        prefix = entity_id.split("-", 1)[0]
        class_name = ENTITY_PREFIX_TO_CLASS.get(prefix)
        if class_name is None:
            continue
        line_idx = _line_index_for_offset(doc.raw, match.start())
        section = _section_for_line(doc.sections, line_idx)
        if section is None:
            continue
        # Compute the hash on the section body so re-imports detect content
        # drift even when the entity_id stayed the same.
        section_text = "\n".join(
            doc.raw.splitlines()[section.line_start : section.line_end]
        )
        entity = ExtractedEntity(
            entity_id=entity_id,
            class_name=class_name,
            source_doc=doc.doc_id,
            source_section=section.title,
            content_hash=hashlib.sha256(section_text.encode("utf-8")).hexdigest(),
            section_line_start=section.line_start,
            section_line_end=section.line_end,
            file_path=doc.file_path,
            mtime=doc.mtime,
        )
        _enrich_extra_slots(entity, section_text)
        seen[entity_id] = entity
    return list(seen.values())


def _enrich_extra_slots(entity: ExtractedEntity, section_text: str) -> None:
    fn = _EXTRA_SLOT_EXTRACTORS.get(entity.class_name)
    if fn is None:
        return
    fn(entity, section_text)
