"""Unit tests for cataforge.domain.docs.migrate_nav."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cataforge.domain.docs.migrate_nav import (
    _parse_nav_table,
    migrate,
)

_VALID_NAV = """\
# CataForge 文档导航

## 文档总览

| Doc ID | 文件路径 | 状态 |
| ------ | -------- | ---- |
| prd | docs/prd/prd-foo-v1.md | draft |
| arch | docs/arch/arch-v1.md | approved |
"""


# ---------------------------------------------------------------------------
# _parse_nav_table
# ---------------------------------------------------------------------------


def test_parse_nav_table_extracts_pairs():
    pairs = _parse_nav_table(_VALID_NAV)
    ids = [p[0] for p in pairs]
    assert "prd" in ids
    assert "arch" in ids


def test_parse_nav_table_skips_header_and_divider():
    pairs = _parse_nav_table(_VALID_NAV)
    ids = [p[0] for p in pairs]
    assert "Doc ID" not in ids
    assert "doc_id" not in ids
    assert "------" not in ids


def test_parse_nav_table_deduplicates():
    duplicate = """\
| prd | docs/prd/prd-v1.md | draft |
| prd | docs/prd/prd-v2.md | approved |
"""
    pairs = _parse_nav_table(duplicate)
    assert len([p for p in pairs if p[0] == "prd"]) == 1


def test_parse_nav_table_empty_text():
    assert _parse_nav_table("") == []


def test_parse_nav_table_only_prose_no_table():
    assert _parse_nav_table("# Just a heading\n\nNo table here.\n") == []


# ---------------------------------------------------------------------------
# migrate — no NAV-INDEX.md → no-op (exit 0)
# ---------------------------------------------------------------------------


def test_migrate_noop_when_no_nav_index(tmp_path: Path, capsys):
    rc = migrate(tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "不存在" in out or "无需迁移" in out


# ---------------------------------------------------------------------------
# migrate — valid NAV-INDEX.md → calls indexer and produces .doc-index.json
# ---------------------------------------------------------------------------


def test_migrate_success_with_valid_nav(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    nav = docs / "NAV-INDEX.md"
    nav.write_text(_VALID_NAV, encoding="utf-8")

    # create the files referenced in the table so the migration can find them
    prd_dir = docs / "prd"
    prd_dir.mkdir()
    (prd_dir / "prd-foo-v1.md").write_text("---\nid: prd\n---\n# PRD\n", encoding="utf-8")

    arch_dir = docs / "arch"
    arch_dir.mkdir()
    (arch_dir / "arch-v1.md").write_text("---\nid: arch\n---\n# ARCH\n", encoding="utf-8")

    # stub out the indexer: write a minimal .doc-index.json and return 0
    def fake_rebuild(project_root: Path) -> int:
        idx = project_root / "docs" / ".doc-index.json"
        idx.write_text('{"documents": {"prd": {}, "arch": {}}}', encoding="utf-8")
        return 0

    with patch("cataforge.domain.docs.migrate_nav._rebuild_index", side_effect=fake_rebuild):
        rc = migrate(tmp_path)

    assert rc == 0
    assert not nav.exists(), "NAV-INDEX.md must be deleted by migration"
    archive_dir = tmp_path / ".cataforge" / ".archive"
    archived = list(archive_dir.glob("NAV-INDEX-*.md"))
    assert archived, "NAV-INDEX.md must be archived"


# ---------------------------------------------------------------------------
# migrate — dry_run skips archive/delete/rebuild
# ---------------------------------------------------------------------------


def test_migrate_dry_run_leaves_nav_intact(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    nav = docs / "NAV-INDEX.md"
    nav.write_text(_VALID_NAV, encoding="utf-8")

    rc = migrate(tmp_path, dry_run=True)
    assert rc == 0
    assert nav.exists(), "dry_run must not delete NAV-INDEX.md"


# ---------------------------------------------------------------------------
# migrate — idempotent: already-migrated project (no NAV-INDEX.md) re-runs fine
# ---------------------------------------------------------------------------


def test_migrate_idempotent_when_already_migrated(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    idx = docs / ".doc-index.json"
    idx.write_text('{"documents": {"prd": {}}}', encoding="utf-8")

    rc = migrate(tmp_path)
    assert rc == 0
    assert idx.read_text(encoding="utf-8") == '{"documents": {"prd": {}}}', (
        "existing .doc-index.json must not be touched when there is no NAV-INDEX.md"
    )
