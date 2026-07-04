"""Per-entity narrative_body capture via the ingest extra-slot path."""

from __future__ import annotations

import hashlib
from pathlib import Path

_BULLET_BODY = (
    "# PRD\n\n## §2 Features\n\n"
    "### F-001 用户登录\n\n"
    "- AC-001: 邮箱密码可登录\n"
    "  续行说明保持缩进\n"
    "- AC-002: 锁定策略生效\n\n"
    "### F-002 占位\n"
)

_NESTED_BODY = (
    "# PRD\n\n### F-001 用户登录\n\n摘要段落。\n\n#### AC-001 邮箱密码可登录\n\n返回 200。\n"
)


def _parsed_doc(doc_id: str, doc_type: str, body: str):
    from cataforge.domain.kg.ingest.scan import (
        ParsedDoc,
        _code_block_char_ranges,
        heading_spans,
    )

    return ParsedDoc(
        doc_id=doc_id,
        doc_type=doc_type,
        file_path=Path(f"{doc_id}.md"),
        mtime=0.0,
        raw=body,
        body=body,
        body_offset=0,
        sections=heading_spans(body, 0),
        code_block_offsets=_code_block_char_ranges(body),
    )


def _extract(body: str):
    from cataforge.domain.kg.ingest.entity_extract import extract_entities

    return {e.scope_key: e for e in extract_entities(_parsed_doc("prd", "prd", body))}


# --- extraction: heading-anchored entities --------------------------------------


def test_feature_narrative_is_section_body_without_heading() -> None:
    entities = _extract(_BULLET_BODY)
    assert entities["F-001"].extra_slots["cf:narrative_body"] == (
        "- AC-001: 邮箱密码可登录\n  续行说明保持缩进\n- AC-002: 锁定策略生效"
    )


def test_parent_narrative_spans_nested_subsections() -> None:
    entities = _extract(_NESTED_BODY)
    assert entities["F-001"].extra_slots["cf:narrative_body"] == (
        "摘要段落。\n\n#### AC-001 邮箱密码可登录\n\n返回 200。"
    )


def test_heading_only_section_omits_narrative_slot() -> None:
    entities = _extract(_BULLET_BODY)
    assert "cf:narrative_body" not in entities["F-002"].extra_slots


# --- extraction: subordinate entities --------------------------------------------


def test_bullet_subordinate_narrative_matches_hash_slice() -> None:
    entities = _extract(_BULLET_BODY)
    ac = entities["F-001/AC-001"]
    narrative = ac.extra_slots["cf:narrative_body"]
    assert narrative == "- AC-001: 邮箱密码可登录\n  续行说明保持缩进"
    assert hashlib.sha256(narrative.encode("utf-8")).hexdigest() == ac.content_hash


def test_own_heading_subordinate_narrative_is_own_section_body() -> None:
    entities = _extract(_NESTED_BODY)
    assert entities["F-001/AC-001"].extra_slots["cf:narrative_body"] == "返回 200。"


# --- write-side: cf:narrative_body triples ----------------------------------------


def test_written_entities_carry_narrative_body_triples() -> None:
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest.entity_extract import extract_entities
    from cataforge.domain.kg.ingest.writer import write_entities, write_project

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    entities = extract_entities(_parsed_doc("prd", "prd", _BULLET_BODY))
    project_iri = write_project(handle.raw, "proj-x", "X", "waterfall", config)
    write_entities(handle.raw, entities, project_iri, config)

    rows = handle.raw.query(
        "PREFIX cf: <https://cataforge.dev/ontology/> "
        "SELECT ?id ?body WHERE { ?s cf:entity_id ?id ; cf:narrative_body ?body }"
    )
    bodies = {row["id"].value: row["body"].value for row in rows}
    assert bodies["F-001"] == (
        "- AC-001: 邮箱密码可登录\n  续行说明保持缩进\n- AC-002: 锁定策略生效"
    )
    assert bodies["AC-001"] == "- AC-001: 邮箱密码可登录\n  续行说明保持缩进"
    assert bodies["AC-002"] == "- AC-002: 锁定策略生效"
    assert "F-002" not in bodies
