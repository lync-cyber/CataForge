"""Phase 3: extract business entities from parsed Markdown.

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
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cataforge.domain.kg.ingest.iri import ENTITY_PREFIX_TO_CLASS
from cataforge.domain.kg.ingest.scan import HeadingSpan, ParsedDoc

_LAYER_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+)", re.MULTILINE)


def _extract_techstack_slots(entity: ExtractedEntity, section_text: str) -> None:
    entity.extra_slots["cf:narrative_body"] = section_text
    layers = [m.group(1).strip() for m in _LAYER_BULLET_RE.finditer(section_text)]
    if layers:
        entity.extra_slots["cf:stack_layers"] = layers


def _labeled_bullet_re(label: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*[-*]\s+{label}\s*[:：]\s*(.+)$", re.MULTILINE | re.IGNORECASE)


_ROUTE_RE = _labeled_bullet_re("Route")
_LAYOUT_RE = _labeled_bullet_re("Layout")
_STATUS_RE = _labeled_bullet_re("Status")
_TASK_STATUS_VALUES = frozenset({"todo", "in_progress", "blocked", "review", "done", "cancelled"})


def _first_labeled_value(pattern: re.Pattern[str], section_text: str) -> str | None:
    m = pattern.search(section_text)
    return m.group(1).strip() if m else None


def _extract_page_slots(entity: ExtractedEntity, section_text: str) -> None:
    route = _first_labeled_value(_ROUTE_RE, section_text)
    if route:
        entity.extra_slots["cf:ui_route"] = route
    layout = _first_labeled_value(_LAYOUT_RE, section_text)
    if layout:
        entity.extra_slots["cf:layout_spec"] = layout


def _extract_task_slots(entity: ExtractedEntity, section_text: str) -> None:
    raw = _first_labeled_value(_STATUS_RE, section_text)
    if raw is None:
        return
    # Normalize "In Progress" / "in-progress" → "in_progress"; drop anything
    # outside TaskStatusEnum so an invalid literal never reaches the store.
    status = re.sub(r"[\s-]+", "_", raw.lower())
    if status in _TASK_STATUS_VALUES:
        entity.extra_slots["cf:task_status"] = status


_EXTRA_SLOT_EXTRACTORS: dict[str, Callable[[ExtractedEntity, str], None]] = {
    "TechStack": _extract_techstack_slots,
    "Page": _extract_page_slots,
    "Task": _extract_task_slots,
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
XREF_RE = re.compile(r"\b(?P<doc>[\w-]+)#§(?P<section>\d+(?:\.\d+)*)\.(?P<entity>[A-Z]+-\d{3,})\b")

# Classes exempt from heading-anchored definition detection: subordinate
# entities attach to a parent section's body (an AcceptanceCriteria sits in
# the bullet list of its owning Feature/Task), not to a heading of their own,
# so they keep first-occurrence semantics.
_TITLE_ANCHOR_EXEMPT_CLASSES = frozenset({"AcceptanceCriteria"})


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


def _inside_code_block(offset: int, ranges: list[tuple[int, int]]) -> bool:
    """Return True when ``offset`` falls inside any of the code/html ``ranges``."""
    return any(start <= offset < end for start, end in ranges)


def _title_defines(title: str, entity_id: str) -> bool:
    """Return True when ``entity_id`` is the subject of heading ``title``.

    The subject is the first entity-id token in the heading (a numbering
    prefix like ``§2.1`` is not an entity-id and does not count). This lets
    ``### §2.1 F-001 用户登录`` define F-001 while ``### T-097: … C-001/C-002``
    defines only T-097 — the trailing component ids are mentions, not
    definitions.
    """
    m = ENTITY_PREFIX_RE.search(title)
    return m is not None and m.group(0) == entity_id


def extract_entities(doc: ParsedDoc) -> list[ExtractedEntity]:
    """Phase 3: scan `doc` for entity_id occurrences.

    A given `entity_id` is emitted at most once per document — at the
    first match, owned by the innermost heading whose span contains it.
    Cross-document duplicates are resolved upstream by
    `migrate.dedupe_entities()` so the canonical definition wins (first
    document in doc_type scan order, typically prd for Feature / AC).

    Xref pattern matches (`prd#§2.F-001` inside an arch document) are
    excluded; otherwise the target entity_id leaks into every doc that
    references it.  Matches inside fenced code blocks, inline code, or
    HTML blocks are also excluded.

    A non-subordinate entity is a *definition* only at the occurrence whose
    owning section heading names it as its subject (see `_title_defines`); a
    bare mention in someone else's section is ignored. Subordinate classes
    (`_TITLE_ANCHOR_EXEMPT_CLASSES`) keep first-occurrence semantics.
    """
    xref_spans = [(m.start(), m.end()) for m in XREF_RE.finditer(doc.raw)]
    code_ranges = doc.code_block_offsets

    def _inside_xref(offset: int) -> bool:
        return any(start <= offset < end for start, end in xref_spans)

    seen: dict[str, ExtractedEntity] = {}
    for match in ENTITY_PREFIX_RE.finditer(doc.raw):
        if _inside_xref(match.start()):
            continue
        if _inside_code_block(match.start(), code_ranges):
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
        # Heading-anchored definition: skip this occurrence when the entity is
        # not the subject of its owning section heading. A later occurrence in
        # the entity's own heading still qualifies (this one wasn't recorded).
        if class_name not in _TITLE_ANCHOR_EXEMPT_CLASSES and not _title_defines(
            section.title, entity_id
        ):
            continue
        # Compute the hash on the section body so re-imports detect content
        # drift even when the entity_id stayed the same.
        section_text = "\n".join(doc.raw.splitlines()[section.line_start : section.line_end])
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


@dataclass
class EntityIdCollision:
    """One entity_id defined in multiple documents with diverging content."""

    entity_id: str
    occurrences: list[tuple[str, str]]  # sorted (source_doc, content_hash) pairs


def detect_entity_id_collisions(
    entities: Iterable[ExtractedEntity],
) -> list[EntityIdCollision]:
    """Flag entity_ids defined in ≥2 source_docs with ≥2 distinct content hashes.

    Instance IRIs are `cfprj:<entity_id>`, so an entity_id is project-global:
    defining the same id in two documents collapses both into one node and the
    last write silently wins. A flagged id means the same identifier carries
    diverging content across documents — cross-document drift, or a definition
    that should have been an xref. The canonical model is define-once /
    reference-by-xref, so callers refuse the import until the source markdown
    is unified. Identical content across docs is a harmless duplicate the
    writer dedups and is not flagged.
    """
    by_id: dict[str, dict[str, str]] = {}
    for entity in entities:
        by_id.setdefault(entity.entity_id, {}).setdefault(entity.source_doc, entity.content_hash)
    collisions: list[EntityIdCollision] = []
    for entity_id, docs in by_id.items():
        if len(docs) >= 2 and len(set(docs.values())) >= 2:
            collisions.append(
                EntityIdCollision(entity_id=entity_id, occurrences=sorted(docs.items()))
            )
    return sorted(collisions, key=lambda c: c.entity_id)


def format_entity_id_collisions(collisions: list[EntityIdCollision]) -> str:
    """Render a collision list into an actionable error message."""
    lines = [
        f"KG import aborted: {len(collisions)} entity_id(s) are defined in "
        "multiple documents with diverging content, which collapses them into "
        "one node and silently loses data.",
        "",
    ]
    lines.extend(
        f"  {c.entity_id}: {', '.join(doc for doc, _ in c.occurrences)}" for c in collisions
    )
    lines.extend(
        [
            "",
            "entity_ids must be project-globally unique. This usually means the "
            "same logical entity was described differently across documents "
            "(cross-document drift). Define each entity in one document and "
            "reference it elsewhere via the xref form `doc_id#§N.ENTITY-ID`. "
            "Unify the source markdown so each entity_id is defined once, then "
            "re-run `cataforge kg import`.",
        ]
    )
    return "\n".join(lines)
