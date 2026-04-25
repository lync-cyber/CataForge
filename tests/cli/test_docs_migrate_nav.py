"""Unit tests for `cataforge docs migrate-nav`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.docs import loader, migrate_nav


@pytest.fixture(autouse=True)
def reset_loader_caches():
    loader._INDEX_CACHE = None
    loader._INDEX_CACHE_ROOT = None
    loader._DOC_TYPE_MAP_CACHE.clear()
    yield
    loader._INDEX_CACHE = None
    loader._INDEX_CACHE_ROOT = None
    loader._DOC_TYPE_MAP_CACHE.clear()


def _make_legacy_project(root: Path, *, with_doc: bool = True) -> Path:
    (root / ".cataforge").mkdir()
    (root / ".cataforge" / "framework.json").write_text(
        json.dumps({"version": "0.1.0"}), encoding="utf-8"
    )
    (root / "docs").mkdir()
    nav = root / "docs" / "NAV-INDEX.md"
    nav.write_text(
        "# NAV-INDEX: demo\n\n"
        "## 文档总览\n\n"
        "| Doc ID | 文件路径 | 状态 | 分卷 | 章节数 |\n"
        "|--------|----------|------|------|--------|\n"
        "| prd | docs/prd/prd-foo-v1.md | draft | 1 | 2 |\n"
        "| arch | docs/arch/arch-foo-v1.md | draft | 1 | 1 |\n",
        encoding="utf-8",
    )
    if with_doc:
        (root / "docs" / "prd").mkdir()
        (root / "docs" / "prd" / "prd-foo-v1.md").write_text(
            "---\nid: prd-foo-v1\ndoc_type: prd\n---\n\n"
            "# PRD\n\n## 1. Overview\nIntro.\n\n## 2. Features\nList.\n",
            encoding="utf-8",
        )
        (root / "docs" / "arch").mkdir()
        (root / "docs" / "arch" / "arch-foo-v1.md").write_text(
            "---\nid: arch-foo-v1\ndoc_type: arch\n---\n\n"
            "# Arch\n\n## 1. Overview\nIntro.\n",
            encoding="utf-8",
        )
    return root


def test_parse_nav_table_extracts_doc_id_path_pairs(tmp_path: Path) -> None:
    nav_text = (
        "## 文档总览\n\n"
        "| Doc ID | 文件路径 |\n"
        "|--------|----------|\n"
        "| prd | docs/prd/prd-foo-v1.md |\n"
        "| arch | docs/arch/arch-foo-v1.md |\n"
        "| ui-spec | docs/ui-spec/ui-spec-foo-v1.md |\n"
    )
    pairs = migrate_nav._parse_nav_table(nav_text)
    assert pairs == [
        ("prd", "docs/prd/prd-foo-v1.md"),
        ("arch", "docs/arch/arch-foo-v1.md"),
        ("ui-spec", "docs/ui-spec/ui-spec-foo-v1.md"),
    ]


def test_parse_nav_table_skips_header_and_divider_rows() -> None:
    nav_text = (
        "| Doc ID | 文件路径 |\n"
        "|--------|----------|\n"
        "| prd | docs/prd/prd-foo-v1.md |\n"
    )
    pairs = migrate_nav._parse_nav_table(nav_text)
    assert pairs == [("prd", "docs/prd/prd-foo-v1.md")]


def test_parse_nav_table_dedupes_duplicate_doc_ids() -> None:
    nav_text = (
        "| prd | docs/prd/prd-foo-v1.md |\n"
        "| prd | docs/prd/prd-foo-v2.md |\n"
    )
    pairs = migrate_nav._parse_nav_table(nav_text)
    assert pairs == [("prd", "docs/prd/prd-foo-v1.md")]


def test_migrate_no_op_when_nav_index_absent(tmp_path: Path, capsys) -> None:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps({"version": "0.1.0"}), encoding="utf-8"
    )
    (tmp_path / "docs").mkdir()

    rc = migrate_nav.migrate(tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "无需迁移" in out


def test_migrate_dry_run_leaves_files_untouched(tmp_path: Path, capsys) -> None:
    root = _make_legacy_project(tmp_path)
    nav = root / "docs" / "NAV-INDEX.md"
    archive = root / ".cataforge" / ".archive"

    rc = migrate_nav.migrate(root, dry_run=True)
    assert rc == 0
    assert nav.exists(), "dry-run must not delete NAV-INDEX.md"
    assert not archive.exists(), "dry-run must not create archive directory"
    assert not (root / "docs" / ".doc-index.json").exists()
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "prd → docs/prd/prd-foo-v1.md" in out


def test_migrate_archives_deletes_and_rebuilds(tmp_path: Path, capsys) -> None:
    root = _make_legacy_project(tmp_path)
    nav = root / "docs" / "NAV-INDEX.md"

    rc = migrate_nav.migrate(root)
    assert rc == 0

    # Archive copy exists
    archive_dir = root / ".cataforge" / ".archive"
    assert archive_dir.is_dir()
    archived = list(archive_dir.glob("NAV-INDEX-*.md"))
    assert len(archived) == 1
    assert "prd | docs/prd/prd-foo-v1.md" in archived[0].read_text(encoding="utf-8")

    # Original removed
    assert not nav.exists()

    # New machine index in place and includes both docs
    idx_path = root / "docs" / ".doc-index.json"
    assert idx_path.is_file()
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    assert "prd-foo-v1" in idx["documents"] or "prd" in idx["documents"]


def test_migrate_warns_on_missing_doc(tmp_path: Path, capsys) -> None:
    """When NAV-INDEX cites a doc that no longer exists, the migration must
    surface it on stderr — that is the orphan case the migration is designed
    to flush out."""
    root = _make_legacy_project(tmp_path, with_doc=False)
    rc = migrate_nav.migrate(root)
    assert rc == 0
    captured = capsys.readouterr()
    # Both prd and arch were in NAV but neither file exists on disk
    assert "未被 indexer 发现" in captured.err
    assert "prd" in captured.err
    assert "arch" in captured.err


def test_migrate_idempotent_second_run_is_noop(tmp_path: Path, capsys) -> None:
    root = _make_legacy_project(tmp_path)
    rc1 = migrate_nav.migrate(root)
    capsys.readouterr()  # drain
    rc2 = migrate_nav.migrate(root)
    assert rc1 == 0 and rc2 == 0
    out = capsys.readouterr().out
    assert "无需迁移" in out
