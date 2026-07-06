"""cataforge unattended build — CLI surface contracts."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cataforge.interface.cli.main import cli
from cataforge.interface.cli.unattended_cmd import _OUTCOME_MESSAGE
from cataforge.runtime.unattended import (
    EXIT_CIRCUIT,
    EXIT_COMPLETE,
    EXIT_MAX_ITERATIONS,
    EXIT_PREFLIGHT,
)


def test_outcome_message_covers_every_exit_code() -> None:
    # Every exit code run_building_loop can return must have a human message —
    # a drift here would otherwise surface as a bare KeyError at runtime.
    assert set(_OUTCOME_MESSAGE) == {
        EXIT_COMPLETE,
        EXIT_CIRCUIT,
        EXIT_MAX_ITERATIONS,
        EXIT_PREFLIGHT,
    }


def _write_claude_md(root: Path, mode: str) -> None:
    (root / "CLAUDE.md").write_text(f"# Proj\n## 项目信息\n- 执行模式: {mode}\n", encoding="utf-8")


def test_preflight_gate_refuses_before_loop(tmp_path: Path) -> None:
    # No dev-plan under the project root → the frozen-upstream gate must refuse
    # with EXIT_PREFLIGHT and never reach the loop (no claude subprocess).
    result = CliRunner().invoke(
        cli,
        ["unattended", "build", "sprint-1", "--project-root", str(tmp_path)],
    )
    assert result.exit_code == EXIT_PREFLIGHT
    assert "拒绝" in result.output


def test_agile_prototype_routes_to_brief_preflight(tmp_path: Path) -> None:
    # 执行模式=agile-prototype + no brief → the brief gate refuses (naming brief),
    # proving mode auto-detection routed away from the dev-plan gate. No sprint arg.
    _write_claude_md(tmp_path, "agile-prototype")
    result = CliRunner().invoke(cli, ["unattended", "build", "--project-root", str(tmp_path)])
    assert result.exit_code == EXIT_PREFLIGHT
    assert "brief" in result.output


def test_non_prototype_missing_sprint_is_usage_error(tmp_path: Path) -> None:
    # standard mode needs an explicit SPRINT; omitting it is a usage error (exit
    # 2), kept distinct from the frozen-upstream refusal (EXIT_PREFLIGHT=5).
    _write_claude_md(tmp_path, "standard")
    result = CliRunner().invoke(cli, ["unattended", "build", "--project-root", str(tmp_path)])
    assert result.exit_code == 2
    assert result.exit_code != EXIT_PREFLIGHT
