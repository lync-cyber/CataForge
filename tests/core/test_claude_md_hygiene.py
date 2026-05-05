"""Unit tests for ``cataforge.core.claude_md_hygiene``."""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.core.claude_md_hygiene import (
    compact_learnings_registry,
    measure_claude_md,
)


def _write_claude_md(path: Path, *, learnings: list[str] | str = "") -> None:
    """Render a minimal CLAUDE.md with a §项目状态 section + the requested
    Learnings Registry shape."""
    if isinstance(learnings, str):
        registry_block = f"- Learnings Registry: {learnings}"
    else:
        if learnings:
            children = "\n".join(f"  - {e}" for e in learnings)
            registry_block = f"- Learnings Registry:\n{children}"
        else:
            registry_block = "- Learnings Registry: (empty)"
    body = (
        "# Test\n"
        "\n"
        "## 项目状态 (orchestrator专属写入区，其他Agent禁止修改)\n"
        "\n"
        "- 当前阶段: development\n"
        f"{registry_block}\n"
        "\n"
        "## 项目信息\n"
        "\n"
        "- 技术栈: cataforge\n"
    )
    path.write_text(body, encoding="utf-8")


class TestMeasureClaudeMd:
    def test_missing_file_returns_zero_counts(self, tmp_path: Path) -> None:
        m = measure_claude_md(tmp_path / "CLAUDE.md")
        assert m.exists is False
        assert m.total_bytes == 0
        assert m.learnings_entries == 0

    def test_counts_inline_registry_with_semicolons(self, tmp_path: Path) -> None:
        path = tmp_path / "CLAUDE.md"
        _write_claude_md(path, learnings="alpha; beta; gamma")
        m = measure_claude_md(path)
        assert m.exists is True
        assert m.learnings_entries == 3
        assert m.state_section_lines > 0

    def test_counts_bullet_children_registry(self, tmp_path: Path) -> None:
        path = tmp_path / "CLAUDE.md"
        _write_claude_md(path, learnings=["one", "two", "three", "four"])
        m = measure_claude_md(path)
        assert m.learnings_entries == 4

    def test_placeholder_value_counts_as_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "CLAUDE.md"
        _write_claude_md(path, learnings="(empty)")
        assert measure_claude_md(path).learnings_entries == 0
        _write_claude_md(path, learnings="—")
        assert measure_claude_md(path).learnings_entries == 0


class TestCompactLearningsRegistry:
    def test_no_op_when_under_limit(self, tmp_path: Path) -> None:
        path = tmp_path / "CLAUDE.md"
        archive = tmp_path / "archive.md"
        _write_claude_md(path, learnings=["one", "two"])
        result = compact_learnings_registry(path, archive_path=archive, max_entries=5)
        assert result.rewrote_claude_md is False
        assert result.archived_entries == 0
        assert not archive.exists()

    def test_keeps_newest_archives_oldest(self, tmp_path: Path) -> None:
        path = tmp_path / "CLAUDE.md"
        archive = tmp_path / "archive.md"
        entries = [f"entry-{i}" for i in range(10)]
        _write_claude_md(path, learnings=entries)
        result = compact_learnings_registry(path, archive_path=archive, max_entries=3)
        assert result.rewrote_claude_md is True
        assert result.archived_entries == 7
        assert result.kept_entries == 3
        # CLAUDE.md only references the newest 3 (entry-7, entry-8, entry-9).
        text = path.read_text(encoding="utf-8")
        assert "entry-7" in text and "entry-8" in text and "entry-9" in text
        for old in entries[:7]:
            assert old not in text
        # Archive contains the trimmed oldest seven, with a today-stamped header.
        archive_text = archive.read_text(encoding="utf-8")
        for old in entries[:7]:
            assert old in archive_text
        # Count headings via line-start prefix (so HTML comments containing
        # the literal `##` substring don't false-positive).
        date_headers = [
            ln for ln in archive_text.splitlines() if ln.startswith("## ")
        ]
        assert len(date_headers) == 1

    def test_subsequent_compaction_appends_archive(self, tmp_path: Path) -> None:
        path = tmp_path / "CLAUDE.md"
        archive = tmp_path / "archive.md"
        _write_claude_md(path, learnings=[f"a{i}" for i in range(8)])
        compact_learnings_registry(path, archive_path=archive, max_entries=2)
        # Append more entries and re-run.
        text = path.read_text(encoding="utf-8")
        new_entries = ["b1", "b2", "b3", "b4", "b5"]
        children = "\n".join(f"  - {e}" for e in ["a6", "a7", *new_entries])
        text = text.replace(
            "- Learnings Registry:\n  - a6\n  - a7",
            f"- Learnings Registry:\n{children}",
        )
        path.write_text(text, encoding="utf-8")
        result = compact_learnings_registry(path, archive_path=archive, max_entries=2)
        assert result.rewrote_claude_md is True
        # First batch + second batch → two `## YYYY-MM-DD` headings (line-start).
        date_headers = [
            ln for ln in archive.read_text(encoding="utf-8").splitlines()
            if ln.startswith("## ")
        ]
        assert len(date_headers) == 2

    def test_missing_file_returns_no_op(self, tmp_path: Path) -> None:
        result = compact_learnings_registry(
            tmp_path / "missing.md",
            archive_path=tmp_path / "archive.md",
            max_entries=3,
        )
        assert result.rewrote_claude_md is False
        assert result.archived_entries == 0

    def test_negative_max_entries_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "CLAUDE.md"
        _write_claude_md(path)
        with pytest.raises(ValueError):
            compact_learnings_registry(
                path, archive_path=tmp_path / "a.md", max_entries=-1
            )
