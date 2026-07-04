"""Entity-level title and content-hash fidelity in the ingest pipeline."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

_BULLET_BODY = (
    "# PRD\n\n## §2 Features\n\n"
    "### F-001 用户登录\n\n"
    "- AC-001: 邮箱密码可登录\n"
    "  续行说明保持缩进\n"
    "- AC-002: 锁定策略生效\n"
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


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- title derivation ---------------------------------------------------------


@pytest.mark.parametrize(
    ("section_title", "expected"),
    [
        ("F-010: 开发者扩展与插件系统", "开发者扩展与插件系统"),
        ("F-010： 开发者扩展与插件系统", "开发者扩展与插件系统"),
        ("F-010 - 用户登录", "用户登录"),
        ("F-010 — 用户登录", "用户登录"),
        ("F-010 – 用户登录", "用户登录"),
        ("F-010 用户登录", "用户登录"),
    ],
)
def test_title_from_section_strips_leading_separators(section_title: str, expected: str) -> None:
    from cataforge.domain.kg.ingest.writer import _title_from_section

    assert _title_from_section(section_title, "F-010") == expected


def test_title_from_section_falls_back_to_entity_id_when_empty() -> None:
    from cataforge.domain.kg.ingest.writer import _title_from_section

    assert _title_from_section("F-010", "F-010") == "F-010"
    assert _title_from_section("F-010:", "F-010") == "F-010"


def test_title_from_line_strips_bullet_marker_and_separator() -> None:
    from cataforge.domain.kg.ingest.writer import _title_from_line

    assert _title_from_line("- AC-001: 用户可以注册插件", "AC-001") == "用户可以注册插件"
    assert _title_from_line("* AC-001 — 插件热加载", "AC-001") == "插件热加载"
    assert _title_from_line("  - AC-001： 全角分隔", "AC-001") == "全角分隔"


def test_title_from_line_strips_table_pipes() -> None:
    from cataforge.domain.kg.ingest.writer import _title_from_line

    assert _title_from_line("| AC-001 | 用户可注册 |", "AC-001") == "用户可注册"


def test_title_from_line_falls_back_to_entity_id_when_empty() -> None:
    from cataforge.domain.kg.ingest.writer import _title_from_line

    assert _title_from_line("- AC-001:", "AC-001") == "AC-001"


# --- extraction: source_line --------------------------------------------------


def test_bullet_subordinate_carries_its_own_line() -> None:
    entities = _extract(_BULLET_BODY)
    assert entities["F-001/AC-001"].source_line == "- AC-001: 邮箱密码可登录"
    assert entities["F-001/AC-002"].source_line == "- AC-002: 锁定策略生效"
    assert entities["F-001"].source_line == ""


def test_own_heading_subordinate_has_no_source_line() -> None:
    body = "# PRD\n\n### F-001 用户登录\n\n#### AC-001 邮箱密码可登录\n\n返回 200。\n"
    entities = _extract(body)
    assert entities["F-001/AC-001"].source_line == ""


# --- extraction: per-entity content hash --------------------------------------


def test_bullet_subordinate_hash_covers_its_own_slice() -> None:
    entities = _extract(_BULLET_BODY)
    assert entities["F-001/AC-001"].content_hash == _sha(
        "- AC-001: 邮箱密码可登录\n  续行说明保持缩进"
    )
    assert entities["F-001/AC-002"].content_hash == _sha("- AC-002: 锁定策略生效")


def test_parent_and_subordinate_hashes_are_all_distinct() -> None:
    entities = _extract(_BULLET_BODY)
    hashes = {e.content_hash for e in entities.values()}
    assert len(hashes) == len(entities)


def test_sibling_bullet_edit_leaves_subordinate_hash_unchanged() -> None:
    before = _extract(_BULLET_BODY)
    after = _extract(_BULLET_BODY.replace("锁定策略生效", "锁定策略已调整"))
    assert before["F-001/AC-001"].content_hash == after["F-001/AC-001"].content_hash
    assert before["F-001/AC-002"].content_hash != after["F-001/AC-002"].content_hash
    assert before["F-001"].content_hash != after["F-001"].content_hash


def test_own_heading_subordinate_keeps_section_hash() -> None:
    body = "# PRD\n\n### F-001 用户登录\n\n#### AC-001 邮箱密码可登录\n\n返回 200。\n"
    entities = _extract(body)
    assert entities["F-001/AC-001"].content_hash == _sha("#### AC-001 邮箱密码可登录\n\n返回 200。")


def test_subordinate_slice_boundaries() -> None:
    from cataforge.domain.kg.ingest.entity_extract import _subordinate_body_slice

    lines = [
        "### F-001 标题",
        "",
        "- AC-001: 第一条",
        "  续行一",
        "  续行二",
        "- AC-002: 第二条",
        "",
        "尾部段落",
    ]
    assert _subordinate_body_slice(lines, 2, len(lines)) == "- AC-001: 第一条\n  续行一\n  续行二"
    assert _subordinate_body_slice(lines, 5, len(lines)) == "- AC-002: 第二条"
    assert _subordinate_body_slice(lines, 2, 4) == "- AC-001: 第一条\n  续行一"


def test_subordinate_slice_stops_at_indented_heading() -> None:
    from cataforge.domain.kg.ingest.entity_extract import _subordinate_body_slice

    lines = ["- AC-001: 第一条", "  续行", "  ### 缩进标题", "  之后"]
    assert _subordinate_body_slice(lines, 0, len(lines)) == "- AC-001: 第一条\n  续行"


# --- write-side: cf:title per entity ------------------------------------------


def test_written_titles_are_entity_specific() -> None:
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
        "SELECT ?id ?t WHERE { ?s cf:entity_id ?id ; cf:title ?t }"
    )
    titles = {row["id"].value: row["t"].value for row in rows}
    assert titles["F-001"] == "用户登录"
    assert titles["AC-001"] == "邮箱密码可登录"
    assert titles["AC-002"] == "锁定策略生效"


# --- migration: hash-driven skip is entity-granular ---------------------------


def test_single_bullet_edit_rewrites_only_touched_entities(tmp_path: Path) -> None:
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    prd_dir = tmp_path / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    prd_path = prd_dir / "prd.md"
    prd_path.write_text("---\ndoc_id: prd\n---\n" + _BULLET_BODY, encoding="utf-8")

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)

    first, _, _ = run_migration(handle.raw, tmp_path, config, doc_types=("prd",))
    assert first.write_stats.entities_written == 3

    prd_path.write_text(
        ("---\ndoc_id: prd\n---\n" + _BULLET_BODY).replace("锁定策略生效", "锁定策略已调整"),
        encoding="utf-8",
    )
    second, _, _ = run_migration(handle.raw, tmp_path, config, doc_types=("prd",))
    assert second.write_stats.entities_written == 2
    assert second.write_stats.entities_skipped == 1
    assert second.verify_result is not None and second.verify_result.ok
