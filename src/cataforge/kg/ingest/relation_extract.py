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

from cataforge.kg.ingest.entity_extract import ENTITY_PREFIX_RE, XREF_RE
from cataforge.kg.ingest.iri import ENTITY_PREFIX_TO_CLASS
from cataforge.kg.ingest.scan import ParsedDoc

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


def infer_predicate(source_class: str | None, target_prefix: str) -> str:
    if source_class is None:
        return DEFAULT_PREDICATE
    return PREDICATE_MAP.get((source_class, target_prefix), DEFAULT_PREDICATE)


def _enclosing_entity(doc: ParsedDoc, offset: int) -> tuple[str, str] | None:
    """Return the (entity_id, class) of the nearest entity_id *before* `offset`."""
    best: tuple[int, str] | None = None
    for match in ENTITY_PREFIX_RE.finditer(doc.raw, 0, offset):
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
    for match in XREF_RE.finditer(doc.raw):
        target_entity_id = match.group("entity")
        target_prefix = target_entity_id.split("-", 1)[0]
        target_class = ENTITY_PREFIX_TO_CLASS.get(target_prefix)
        if target_class is None:
            continue
        enclosing = _enclosing_entity(doc, match.start())
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
            )
        )
    return relations
