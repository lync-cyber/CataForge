"""Doc-type definition authority in the ingest pipeline.

An entity class's definition is recognized only in its authoritative
doc_type(s); a heading-subject or subordinate occurrence anywhere else is a
reference, not a definition. Projects extend (never narrow) the per-class
default via framework.json `context.kg_definition_authority`.
"""

from __future__ import annotations

import json
from pathlib import Path


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


def _scope_keys(doc_type: str, body: str) -> set[str]:
    from cataforge.domain.kg.ingest.entity_extract import extract_entities

    return {e.scope_key for e in extract_entities(_parsed_doc(doc_type, doc_type, body))}


_TASK_SECTION_BODY = (
    "# Doc\n\n## §2 任务\n\n### T-087: 迁移引导\n\n- AC-001: 引导文案包含来源章节\n"
)


def test_non_authoritative_heading_subject_is_a_reference() -> None:
    # A test-report broken down by task re-states T-087 as a heading subject;
    # Task definitions belong to dev-plan, so no definition is minted here.
    assert "T-087" not in _scope_keys("test-report", _TASK_SECTION_BODY)


def test_non_authoritative_subordinate_follows_parent_authority() -> None:
    # The bare AC under the task section resolves its parent to T-087 (a
    # Task), so its authority is dev-plan too — skipped in test-report.
    keys = _scope_keys("test-report", _TASK_SECTION_BODY)
    assert "T-087/AC-001" not in keys
    assert not any(k.endswith("AC-001") for k in keys)


def test_authoritative_doc_type_still_defines() -> None:
    keys = _scope_keys("dev-plan", _TASK_SECTION_BODY)
    assert {"T-087", "T-087/AC-001"} <= keys


def test_subordinate_authority_tracks_parent_class() -> None:
    feature_body = "# Doc\n\n### F-001 登录\n\n- AC-001: 邮箱密码可登录\n"
    assert "F-001/AC-001" in _scope_keys("prd", feature_body)
    assert "F-001/AC-001" not in _scope_keys("dev-plan", feature_body)


def test_parentless_subordinate_uses_its_own_class_authority() -> None:
    body = "# Doc\n\n## §2 验收\n\n### AC-001 用户可登录\n\n返回 200。\n"
    assert "AC-001" in _scope_keys("prd", body)
    assert "AC-001" not in _scope_keys("dev-plan", body)


def test_default_authority_covers_every_ingest_class() -> None:
    from cataforge.domain.kg._config import (
        BUSINESS_DOC_TYPES,
        DEFAULT_DEFINITION_AUTHORITY,
    )
    from cataforge.domain.kg.ingest.iri import ENTITY_PREFIX_TO_CLASS

    missing = set(ENTITY_PREFIX_TO_CLASS.values()) - set(DEFAULT_DEFINITION_AUTHORITY)
    assert not missing, f"ingest classes with no definition authority: {missing}"
    for class_name, doc_types in DEFAULT_DEFINITION_AUTHORITY.items():
        assert doc_types, f"{class_name} has an empty authority set"
        assert doc_types <= set(BUSINESS_DOC_TYPES), (
            f"{class_name} authority {doc_types} outside the business doc_type universe"
        )


# --- framework.json extension resolution --------------------------------------


def _write_framework_json(project_root: Path, payload: dict) -> None:
    cfg_dir = project_root / ".cataforge"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "framework.json").write_text(json.dumps(payload), encoding="utf-8")


def test_definition_authority_defaults_without_config(tmp_path: Path) -> None:
    from cataforge.domain.kg._dispatch import definition_authority

    authority = definition_authority(tmp_path)
    assert authority["Task"] == frozenset({"dev-plan"})
    assert authority["Feature"] == frozenset({"prd"})
    assert authority["TestCase"] == frozenset({"test-report"})


def test_definition_authority_extension_merges_per_class(tmp_path: Path) -> None:
    from cataforge.domain.kg._dispatch import definition_authority, invalidate_cache

    _write_framework_json(
        tmp_path,
        {"context": {"kg_definition_authority": {"Task": ["test-report"]}}},
    )
    invalidate_cache()
    authority = definition_authority(tmp_path)
    assert authority["Task"] == frozenset({"dev-plan", "test-report"})
    assert authority["Feature"] == frozenset({"prd"})


def test_definition_authority_ignores_malformed_entries(tmp_path: Path) -> None:
    from cataforge.domain.kg._dispatch import definition_authority, invalidate_cache

    _write_framework_json(
        tmp_path,
        {
            "context": {
                "kg_definition_authority": {
                    "Task": "test-report",
                    "Feature": ["arch", 3],
                }
            }
        },
    )
    invalidate_cache()
    authority = definition_authority(tmp_path)
    assert authority["Task"] == frozenset({"dev-plan"})
    assert authority["Feature"] == frozenset({"prd"})


# --- migration integration ----------------------------------------------------


def _write_doc(project_root: Path, doc_type: str, name: str, body: str) -> None:
    d = project_root / "docs" / doc_type
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def test_run_migration_tolerates_task_sections_in_test_report(tmp_path: Path) -> None:
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    _write_doc(
        tmp_path,
        "dev-plan",
        "dev-plan.md",
        "---\ndoc_id: dev-plan\n---\n# Dev Plan\n\n## §5 Tasks\n\n"
        "### T-087 迁移引导\n\n- AC-001: 引导文案包含来源章节\n",
    )
    _write_doc(
        tmp_path,
        "test-report",
        "test-report.md",
        "---\ndoc_id: test-report\n---\n# Test Report\n\n## §2 任务结果\n\n"
        "### T-087: 迁移引导（实测）\n\n- AC-001: 实测通过\n",
    )

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)

    stats, entities, _ = run_migration(
        handle.raw, tmp_path, config, doc_types=("dev-plan", "test-report")
    )
    assert {e.scope_key for e in entities} == {"T-087", "T-087/AC-001"}
    assert {e.source_doc for e in entities} == {"dev-plan"}
    assert stats.verify_result is not None and stats.verify_result.ok


def test_run_migration_honours_authority_extension(tmp_path: Path) -> None:
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.domain.kg.ingest import run_migration

    _write_framework_json(
        tmp_path,
        {"context": {"kg_definition_authority": {"Glossary": ["arch"]}}},
    )
    invalidate_cache()
    _write_doc(
        tmp_path,
        "arch",
        "arch.md",
        "---\ndoc_id: arch\n---\n# Arch\n\n## §7 术语\n\n### GL-001 领域术语\n\n图谱即事实源。\n",
    )

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)

    _, entities, _ = run_migration(handle.raw, tmp_path, config, doc_types=("arch",))
    assert {e.entity_id for e in entities} == {"GL-001"}
    assert entities[0].source_doc == "arch"
