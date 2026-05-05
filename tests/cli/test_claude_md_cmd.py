"""Tests for ``cataforge claude-md`` (check + compact)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli.claude_md_cmd import check_command, compact_command


def _bootstrap(
    tmp_path: Path,
    *,
    learnings: list[str] | None = None,
    limits: dict[str, int] | None = None,
) -> Path:
    (tmp_path / ".cataforge").mkdir()
    payload = {"version": "0.0.0-test", "runtime": {"platform": "claude-code"}}
    if limits:
        payload["claude_md_limits"] = limits
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    children = ""
    if learnings:
        children = "\n" + "\n".join(f"  - {e}" for e in learnings)
    (tmp_path / "CLAUDE.md").write_text(
        "# Test\n\n"
        "## 项目状态 (orchestrator专属写入区，其他Agent禁止修改)\n\n"
        "- 当前阶段: development\n"
        f"- Learnings Registry:{children}\n"
        "\n"
        "## 项目信息\n",
        encoding="utf-8",
    )
    return tmp_path


class TestCheckCommand:
    def test_passes_under_limits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path, learnings=["one", "two"])
        monkeypatch.chdir(project)
        result = CliRunner().invoke(check_command, [])
        assert result.exit_code == 0, result.output
        assert "OK" in result.output

    def test_fails_when_registry_overflows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(
            tmp_path,
            learnings=[f"e{i}" for i in range(20)],
            limits={"learnings_registry_max_entries": 5},
        )
        monkeypatch.chdir(project)
        result = CliRunner().invoke(check_command, [])
        assert result.exit_code == 1
        assert "registry exceeds max" in result.output

    def test_missing_claude_md_is_informational(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".cataforge").mkdir()
        (tmp_path / ".cataforge" / "framework.json").write_text(
            json.dumps({"version": "0.0.0-test"}), encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(check_command, [])
        assert result.exit_code == 0
        assert "No CLAUDE.md" in result.output


class TestCompactCommand:
    def test_no_op_when_under_limit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(tmp_path, learnings=["a", "b"])
        monkeypatch.chdir(project)
        result = CliRunner().invoke(compact_command, [])
        assert result.exit_code == 0
        assert "no compaction needed" in result.output

    def test_compacts_overflow_to_archive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(
            tmp_path,
            learnings=[f"item-{i}" for i in range(15)],
            limits={"learnings_registry_max_entries": 4},
        )
        monkeypatch.chdir(project)
        result = CliRunner().invoke(compact_command, [])
        assert result.exit_code == 0, result.output
        assert "archived 11" in result.output
        archive = project / ".cataforge" / "learnings" / "registry-archive.md"
        assert archive.is_file()
        archive_text = archive.read_text(encoding="utf-8")
        for i in range(11):
            assert f"- item-{i}\n" in archive_text
        # Newest 4 stay in CLAUDE.md.
        claude_text = (project / "CLAUDE.md").read_text(encoding="utf-8")
        for i in range(11, 15):
            assert f"item-{i}\n" in claude_text
        # Trimmed entries gone (match exact bullet form to avoid
        # item-1 vs item-11 substring overlap).
        for i in range(11):
            assert f"- item-{i}\n" not in claude_text

    def test_dry_run_does_not_modify_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _bootstrap(
            tmp_path,
            learnings=[f"e{i}" for i in range(10)],
            limits={"learnings_registry_max_entries": 3},
        )
        monkeypatch.chdir(project)
        before = (project / "CLAUDE.md").read_text(encoding="utf-8")
        result = CliRunner().invoke(compact_command, ["--dry-run"])
        assert result.exit_code == 0
        assert "would archive" in result.output
        after = (project / "CLAUDE.md").read_text(encoding="utf-8")
        assert before == after
        assert not (project / ".cataforge" / "learnings" / "registry-archive.md").exists()
