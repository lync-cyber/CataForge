"""Phase 4: extract cross-document traceability edges.

A traceability edge appears in source Markdown as `doc_id#§N.ITEM`
(strict coverage mode). The codemod locates the nearest enclosing
entity_id (the subject) and infers a predicate from the
(source_class, target_prefix) pair, falling back to the generic
`cf:depends_on` when no specific predicate is known.

The predicates returned here are CURIEs against the business ontology
namespace (`cf:`); phase 5 expands them to full IRIs at write time.
"""

from __future__ import annotations

from dataclasses import dataclass

from cataforge.domain.kg.ingest.entity_extract import (
    ENTITY_PREFIX_RE,
    XREF_RE,
    _inside_code_block,
    _line_index_for_offset,
)
from cataforge.domain.kg.ingest.iri import ENTITY_PREFIX_TO_CLASS
from cataforge.domain.kg.ingest.scan import HeadingSpan, ParsedDoc

# Source class × target prefix → predicate CURIE.
# Uses slot names from core.yaml (e.g. `cf:implements`). Schema is the
# source of truth — see `core.yaml` slot definitions.
PREDICATE_MAP: dict[tuple[str, str], str] = {
    ("Module", "F"): "cf:implements",
    ("Component", "F"): "cf:implements",
    ("Page", "F"): "cf:satisfies",
    ("UIComponent", "F"): "cf:satisfies",
    ("Task", "M"): "cf:realizes",
    ("Task", "API"): "cf:realizes",
    ("Task", "C"): "cf:realizes",
    ("Task", "AC"): "cf:satisfies",
    ("TestCase", "T"): "cf:verifies",
    ("TestCase", "AC"): "cf:verifies",
    ("TestCase", "F"): "cf:verifies",
    ("API", "F"): "cf:satisfies",
    ("AcceptanceCriteria", "F"): "cf:satisfies",
}
DEFAULT_PREDICATE = "cf:depends_on"


@dataclass
class ExtractedRelation:
    """A single cross-document traceability edge captured during phase 4."""

    subject_entity_id: str
    subject_class: str
    predicate_curie: str
    object_entity_id: str
    object_class: str
    source_doc: str
    object_doc: str | None = None


def infer_predicate(source_class: str | None, target_prefix: str) -> str:
    if source_class is None:
        return DEFAULT_PREDICATE
    return PREDICATE_MAP.get((source_class, target_prefix), DEFAULT_PREDICATE)


def _section_for_offset(doc: ParsedDoc, offset: int) -> HeadingSpan | None:
    """Return the deepest HeadingSpan that contains ``offset`` (char-based)."""
    line_idx = _line_index_for_offset(doc.raw, offset)
    candidates = [s for s in doc.sections if s.line_start <= line_idx < s.line_end]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.level)


def _enclosing_entity(
    doc: ParsedDoc,
    offset: int,
    *,
    xref_section: HeadingSpan | None,
    xref_spans: list[tuple[int, int]],
) -> tuple[str, str] | None:
    """Return (entity_id, class) of the nearest entity_id before ``offset``.

    Search is restricted to the same HeadingSpan as the xref when
    ``xref_section`` is provided, preventing cross-section pollution.
    Candidates inside fenced code blocks, inline code, or HTML blocks are
    skipped, as are entity_ids that are themselves the target of another xref
    (so a second xref on the same line binds to the section's subject, not to
    the first xref's ``.ITEM`` component).
    """
    if xref_section is not None:
        # Convert section line bounds back to char offsets for the search window.
        lines = doc.raw.splitlines(keepends=True)
        cumoffsets = [0]
        for line in lines:
            cumoffsets.append(cumoffsets[-1] + len(line))
        section_start_char = (
            cumoffsets[xref_section.line_start] if xref_section.line_start < len(cumoffsets) else 0
        )
        search_start = section_start_char
    else:
        search_start = 0

    best: tuple[int, str] | None = None
    for match in ENTITY_PREFIX_RE.finditer(doc.raw, search_start, offset):
        if _inside_code_block(match.start(), doc.code_block_offsets):
            continue
        if any(start <= match.start() < end for start, end in xref_spans):
            continue
        if best is None or match.start() > best[0]:
            best = (match.start(), match.group(0))

    if best is None:
        return None
    entity_id = best[1]
    prefix = entity_id.split("-", 1)[0]
    class_name = ENTITY_PREFIX_TO_CLASS.get(prefix)
    if class_name is None:
        return None
    return entity_id, class_name


def extract_relations(doc: ParsedDoc) -> list[ExtractedRelation]:
    """Phase 4: scan `doc` for `doc_id#§N.ITEM` xref pairs."""
    relations: list[ExtractedRelation] = []
    xref_spans = [(m.start(), m.end()) for m in XREF_RE.finditer(doc.raw)]
    for match in XREF_RE.finditer(doc.raw):
        target_entity_id = match.group("entity")
        target_prefix = target_entity_id.split("-", 1)[0]
        target_class = ENTITY_PREFIX_TO_CLASS.get(target_prefix)
        if target_class is None:
            continue
        xref_section = _section_for_offset(doc, match.start())
        enclosing = _enclosing_entity(
            doc, match.start(), xref_section=xref_section, xref_spans=xref_spans
        )
        if enclosing is None:
            continue
        subject_entity_id, subject_class = enclosing
        if subject_entity_id == target_entity_id:
            # Self-reference inside a section header — skip.
            continue
        predicate = infer_predicate(subject_class, target_prefix)
        relations.append(
            ExtractedRelation(
                subject_entity_id=subject_entity_id,
                subject_class=subject_class,
                predicate_curie=predicate,
                object_entity_id=target_entity_id,
                object_class=target_class,
                source_doc=doc.doc_id,
                object_doc=match.group("doc"),
            )
        )
    return relations
