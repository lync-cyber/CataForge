"""Heading-anchored definition detection.

A non-subordinate entity is a *definition* only at the occurrence whose
owning section heading names it as its subject; a bare mention in another
entity's section body mints no node and triggers no cross-document
collision. Subordinate classes (AcceptanceCriteria) keep
first-occurrence semantics.
"""

from __future__ import annotations

from pathlib import Path


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


def _ids(body: str, doc_type: str = "prd") -> set[str]:
    from cataforge.domain.kg.ingest.entity_extract import extract_entities

    return {e.entity_id for e in extract_entities(_parsed_doc(doc_type, doc_type, body))}


def test_numbered_heading_still_defines_its_subject() -> None:
    # `§2.1` is a numbering prefix, not an entity id, so F-001 is still the
    # heading subject and gets defined.
    assert "F-001" in _ids("# PRD\n\n## §2 Features\n\n### §2.1 F-001 用户登录\n\n正文。\n")


def test_bare_mention_in_another_section_is_not_a_definition() -> None:
    body = (
        "# Arch\n\n## §2 Modules\n\n"
        "### E-008 DiagnosticReport\n\n"
        "该报告依赖 F-002 的视觉一致性约束。\n"
    )
    ids = _ids(body, doc_type="arch")
    assert "E-008" in ids
    assert "F-002" not in ids, "a bare mention in E-008's body must not define F-002"


def test_only_heading_subject_defined_not_listed_components() -> None:
    # A task card whose title lists component ids defines only the task; the
    # trailing component ids are mentions (the genuine_multi case).
    body = "# Dev Plan\n\n## §5 Tasks\n\n### T-097 设计 — C-001/C-002/C-003\n\n正文。\n"
    ids = _ids(body, doc_type="dev-plan")
    assert ids == {"T-097"}


def test_acceptance_criteria_in_parent_body_stays_exempt() -> None:
    # AC lives in its owning Feature's bullet list with no heading of its own;
    # it must still be extracted despite heading anchoring.
    body = "# PRD\n\n## §2 Features\n\n### F-001 用户登录\n\n- AC-001: 邮箱密码可登录\n"
    ids = _ids(body)
    assert {"F-001", "AC-001"} <= ids


def test_cross_doc_mention_no_longer_collides() -> None:
    from cataforge.domain.kg.ingest.entity_extract import (
        detect_entity_id_collisions,
        extract_entities,
    )

    prd = _parsed_doc(
        "prd", "prd", "# PRD\n\n## §2 Features\n\n### F-002 视觉一致性\n\n预览要一致。\n"
    )
    arch = _parsed_doc(
        "arch",
        "arch",
        "# Arch\n\n## §3 Data\n\n### E-008 DiagnosticReport\n\n依赖 F-002 的视觉。\n",
    )
    entities = extract_entities(prd) + extract_entities(arch)
    # F-002 is defined only in prd; arch merely mentions it → no collision.
    assert detect_entity_id_collisions(entities) == []
    assert {e.source_doc for e in entities if e.entity_id == "F-002"} == {"prd"}


def test_xref_mention_still_becomes_a_relation_edge() -> None:
    # D3: tightening definition detection must not drop the xref edge — the
    # mention `prd#§2.F-001` inside M-001's body still yields an implements edge.
    from cataforge.domain.kg.ingest.relation_extract import extract_relations

    body = "# Arch\n\n## §2 Modules\n\n### M-001 认证模块\n\n- 映射功能: prd#§2.F-001\n"
    relations = extract_relations(_parsed_doc("arch", "arch", body))
    edge = [r for r in relations if r.object_entity_id == "F-001"]
    assert edge, "xref to F-001 must still produce a relation edge"
    assert edge[0].subject_entity_id == "M-001"
    assert edge[0].predicate_curie == "cf:implements"
