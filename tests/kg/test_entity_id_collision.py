"""Cross-document entity_id collision detection.

The flat `cfprj:<entity_id>` IRI scheme makes entity_ids project-global.
When the same id is *defined* (not xref-referenced) in two doc_types with
diverging content, the writer collapses them into one node and silently
loses data. Import must refuse such a project so the author unifies the
source markdown first.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.domain.kg.ingest.entity_extract import (
    ExtractedEntity,
    detect_entity_id_collisions,
)


def _entity(entity_id: str, source_doc: str, content_hash: str) -> ExtractedEntity:
    return ExtractedEntity(
        entity_id=entity_id,
        class_name="AcceptanceCriteria",
        source_doc=source_doc,
        source_section=f"{entity_id} title",
        content_hash=content_hash,
        section_line_start=0,
        section_line_end=1,
        file_path=Path(f"{source_doc}.md"),
        mtime=0.0,
    )


def test_detect_flags_same_id_across_docs_with_diverging_content() -> None:
    collisions = detect_entity_id_collisions(
        [
            _entity("AC-001", "prd", "a" * 64),
            _entity("AC-001", "dev-plan", "b" * 64),
            _entity("F-001", "prd", "c" * 64),
        ]
    )
    assert [c.entity_id for c in collisions] == ["AC-001"]
    assert collisions[0].occurrences == [("dev-plan", "b" * 64), ("prd", "a" * 64)]


def test_detect_ignores_identical_content_across_docs() -> None:
    # Same id, two docs, but identical content_hash → harmless duplicate the
    # writer dedups; not a collision.
    collisions = detect_entity_id_collisions(
        [
            _entity("F-001", "prd", "a" * 64),
            _entity("F-001", "arch", "a" * 64),
        ]
    )
    assert collisions == []


def test_detect_ignores_single_doc_definition() -> None:
    collisions = detect_entity_id_collisions(
        [
            _entity("AC-001", "prd", "a" * 64),
            _entity("AC-002", "prd", "b" * 64),
        ]
    )
    assert collisions == []


def _write(project_root: Path, doc_type: str, name: str, body: str) -> None:
    d = project_root / "docs" / doc_type
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def test_run_migration_raises_on_cross_doc_collision(tmp_path: Path) -> None:
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg._errors import KGEntityCollisionError
    from cataforge.domain.kg.ingest import run_migration

    _write(
        tmp_path,
        "prd",
        "prd-x.md",
        "# PRD\n\n## §2 AC\n\n### AC-001 用户可登录\n\n登录成功返回 200。\n",
    )
    _write(
        tmp_path,
        "dev-plan",
        "dev-plan-x.md",
        "# Dev Plan\n\n## §5 Tasks\n\n### AC-001 任务验收\n\n覆盖率不低于 80%。\n",
    )

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)

    with pytest.raises(KGEntityCollisionError) as excinfo:
        run_migration(handle.raw, tmp_path, config, doc_types=("prd", "dev-plan"))

    msg = str(excinfo.value)
    assert "AC-001" in msg
    assert "prd" in msg and "dev-plan" in msg
    # Nothing written — the gate fires before phase 5.
    rows = list(
        handle.raw.query(
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "SELECT (COUNT(?s) AS ?n) WHERE { ?s cf:entity_id ?id }"
        )
    )
    assert int(rows[0]["n"].value) == 0


def test_run_migration_allows_identical_cross_doc_mention(tmp_path: Path) -> None:
    """A cross-doc re-mention with identical section content dedups cleanly
    rather than aborting — only diverging content is a collision."""
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    shared = "# Doc\n\n## §1 F\n\n### F-001 用户登录\n\n同一段内容。\n"
    _write(tmp_path, "prd", "prd-x.md", shared)
    _write(tmp_path, "arch", "arch-x.md", shared)

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)

    stats, entities, _ = run_migration(handle.raw, tmp_path, config, doc_types=("prd", "arch"))
    assert {e.entity_id for e in entities} == {"F-001"}
    assert stats.verify_result is not None and stats.verify_result.ok


def test_run_migration_ignores_bare_ac_mention_without_parent(tmp_path: Path) -> None:
    """A parent-local AC id mentioned in prose under a non-entity heading
    (`F-001 AC-001` in a tech-stack table) is a reference, not a definition: it
    must mint no phantom global node and must not collide with the genuine
    parent-scoped AC defined elsewhere."""
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    # prd defines AC-001 under its Feature; arch only *mentions* it in a table.
    _write(
        tmp_path,
        "prd",
        "prd-x.md",
        "# PRD\n\n## F-001 写作体验\n\n- AC-001: 用户可登录，返回 200。\n",
    )
    _write(
        tmp_path,
        "arch",
        "arch-x.md",
        "# ARCH\n\n## 1.4 技术栈\n\n| 测试 | Vitest | F-001 AC-001 跨运行时一致 |\n",
    )

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)

    # No KGEntityCollisionError despite AC-001 appearing in both documents.
    _, entities, _ = run_migration(handle.raw, tmp_path, config, doc_types=("prd", "arch"))
    scope_keys = {e.scope_key for e in entities}
    assert "F-001/AC-001" in scope_keys
    assert "AC-001" not in scope_keys
