"""``cataforge doctor`` integration: CLAUDE.md hygiene section."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.interface.cli.doctor_cmd import doctor_command


def _project_with_claude_md(
    tmp_path: Path,
    *,
    learnings_count: int,
    max_entries: int,
) -> Path:
    cf = tmp_path / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps(
            {
                "version": "0.0.0-test",
                "runtime_api_version": "1.0",
                "claude_md_limits": {
                    "learnings_registry_max_entries": max_entries,
                    "max_bytes": 100000,
                    "max_state_section_lines": 200,
                },
            }
        ),
        encoding="utf-8",
    )
    children = "\n".join(f"  - e{i}" for i in range(learnings_count))
    (tmp_path / "CLAUDE.md").write_text(
        f"# Test\n\n## 项目状态\n\n- 当前阶段: development\n- Learnings Registry:\n{children}\n",
        encoding="utf-8",
    )
    return tmp_path


def test_doctor_reports_hygiene_section(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _project_with_claude_md(tmp_path, learnings_count=3, max_entries=10)
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert "CLAUDE.md hygiene" in result.output
    assert "Learnings Registry: " in result.output


def test_doctor_fails_when_learnings_overflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project_with_claude_md(tmp_path, learnings_count=15, max_entries=5)
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 1
    assert "Learnings Registry over limit" in result.output


def test_hygiene_fails_on_overlong_state_bullet(tmp_path: Path, capsys) -> None:
    """An overlong §项目状态 bullet is a gating FAIL — a single run-on line
    accumulating history is exactly the bloat the guard must block."""
    from dataclasses import dataclass

    from cataforge.interface.cli.doctor.hygiene import check_claude_md_hygiene

    @dataclass
    class _FakePaths:
        root: Path

    @dataclass
    class _FakeCfg:
        paths: _FakePaths
        claude_md_limits: dict[str, int]

    long_bullet = "上次完成: " + "x" * 300
    (tmp_path / "CLAUDE.md").write_text(
        f"# Test\n\n## 项目状态\n\n- 当前阶段: development\n- {long_bullet}\n",
        encoding="utf-8",
    )
    cfg = _FakeCfg(
        paths=_FakePaths(root=tmp_path),
        claude_md_limits={
            "max_bytes": 100000,
            "max_state_section_lines": 200,
            "learnings_registry_max_entries": 10,
            "max_state_bullet_chars": 100,
        },
    )

    failed = check_claude_md_hygiene(cfg)  # type: ignore[arg-type]
    out = capsys.readouterr().out

    assert failed == 1, out
    assert "bullet" in out.lower()


def test_hygiene_passes_on_bullet_within_limit(tmp_path: Path, capsys) -> None:
    """A §项目状态 bullet under the limit does not gate."""
    from dataclasses import dataclass

    from cataforge.interface.cli.doctor.hygiene import check_claude_md_hygiene

    @dataclass
    class _FakePaths:
        root: Path

    @dataclass
    class _FakeCfg:
        paths: _FakePaths
        claude_md_limits: dict[str, int]

    (tmp_path / "CLAUDE.md").write_text(
        "# Test\n\n## 项目状态\n\n- 当前阶段: development\n- 上次完成: reviewer — arch approved\n",
        encoding="utf-8",
    )
    cfg = _FakeCfg(
        paths=_FakePaths(root=tmp_path),
        claude_md_limits={
            "max_bytes": 100000,
            "max_state_section_lines": 200,
            "learnings_registry_max_entries": 10,
            "max_state_bullet_chars": 250,
        },
    )

    failed = check_claude_md_hygiene(cfg)  # type: ignore[arg-type]
    assert failed == 0, capsys.readouterr().out


def test_doctor_passes_without_claude_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cf = tmp_path / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.0.0-test", "runtime_api_version": "1.0"}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(doctor_command, [])
    # No CLAUDE.md → informational only, hygiene section can't fail.
    assert "CLAUDE.md hygiene" in result.output
    assert "no CLAUDE.md" in result.output
