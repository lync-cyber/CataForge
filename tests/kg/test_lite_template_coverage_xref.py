"""Lite-template coverage fields are strict `doc_id#§N.ITEM` xrefs.

The relation extractor only mints traceability edges from strict xref form;
bare-prose coverage fields (`对应功能: F-001`) yield zero edges. These tests
pin the agile-lite templates to the xref form so write-doc / ingest populate
the coverage graph the doc-review gates depend on.
"""

from __future__ import annotations

import re
from pathlib import Path

from cataforge.domain.kg.ingest.relation_extract import ExtractedRelation, extract_relations

LITE_DIR = (
    Path(__file__).resolve().parents[2] / ".cataforge" / "skills" / "context" / "templates" / "lite"
)


def _fill(text: str) -> str:
    """Instantiate a template: replace every ``{placeholder}`` with a slug."""
    return re.sub(r"\{[^{}]*\}", "demo", text)


def _parsed_doc(doc_id: str, doc_type: str, body: str):
    from cataforge.domain.kg.ingest.scan import (
        ParsedDoc,
        _code_block_char_ranges,
        _heading_spans,
    )

    return ParsedDoc(
        doc_id=doc_id,
        doc_type=doc_type,
        file_path=Path(f"{doc_id}.md"),
        mtime=0.0,
        raw=body,
        body=body,
        body_offset=0,
        sections=_heading_spans(body, 0),
        code_block_offsets=_code_block_char_ranges(body),
    )


def _relations(doc_id: str, doc_type: str, body: str) -> list[ExtractedRelation]:
    return extract_relations(_parsed_doc(doc_id, doc_type, body))


def _triples(rels: list[ExtractedRelation]) -> set[tuple[str, str, str]]:
    return {(r.subject_entity_id, r.predicate_curie, r.object_entity_id) for r in rels}


def _template(name: str) -> str:
    return _fill((LITE_DIR / name).read_text(encoding="utf-8"))


def test_arch_template_coverage_uses_xref_and_extracts_implements() -> None:
    rels = _relations("arch-lite-demo", "arch", _template("arch-lite.md"))
    triples = _triples(rels)
    assert ("M-001", "cf:implements", "F-001") in triples
    assert ("M-001", "cf:implements", "F-002") in triples
    assert ("M-002", "cf:implements", "F-003") in triples


def test_ui_spec_template_coverage_uses_xref_and_extracts_satisfies() -> None:
    rels = _relations("ui-spec-lite-demo", "ui-spec", _template("ui-spec-lite.md"))
    triples = _triples(rels)
    assert ("UC-001", "cf:satisfies", "F-001") in triples
    assert ("UC-002", "cf:satisfies", "F-002") in triples


def test_dev_plan_template_coverage_uses_xref_and_extracts_realizes() -> None:
    rels = _relations("dev-plan-lite-demo", "dev-plan", _template("dev-plan-lite.md"))
    triples = _triples(rels)
    assert ("T-001", "cf:realizes", "M-001") in triples
    assert ("T-002", "cf:realizes", "M-002") in triples


def test_relation_subject_binds_to_entity_not_trailing_ac() -> None:
    """A coverage xref under a Task heading binds to the Task, never to a
    subordinate AcceptanceCriteria sitting later in the same section."""
    body = (
        "# Dev Plan\n\n## §1 任务清单\n\n"
        "### T-001 登录任务\n"
        "- **模块**: arch-lite-demo#§2.M-001\n"
        "- **tdd_acceptance**:\n"
        "  - AC-001: Given 已注册, When 提交, Then 登录成功\n"
    )
    triples = _triples(_relations("dev-plan-lite-demo", "dev-plan", body))
    assert ("T-001", "cf:realizes", "M-001") in triples
    assert not any(s.startswith("AC-") for s, _p, _o in triples)
