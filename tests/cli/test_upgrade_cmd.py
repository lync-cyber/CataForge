"""Tests for ``cataforge upgrade {apply,rollback,check}``.

Exercise the rollback loop and the CHANGELOG BREAKING detection in-process
via ``CliRunner`` — much faster than spinning up the e2e venv and sufficient
for the parts that don't need a real wheel.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli.main import cli
from cataforge.cli.upgrade_cmd import _find_breaking_entries


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scaffolded project with cwd pointed at it."""
    from cataforge.core.scaffold import copy_scaffold_to

    root = tmp_path / "proj"
    root.mkdir()
    copy_scaffold_to(root / ".cataforge", force=False)
    monkeypatch.chdir(root)
    return root


def test_upgrade_apply_creates_backup_and_reports_it(
    runner: CliRunner, project: Path
) -> None:
    """`apply` on an existing scaffold must echo the backup path."""
    target_agent = next((project / ".cataforge" / "agents").rglob("AGENT.md"))
    target_agent.write_text("custom\n", encoding="utf-8")

    result = runner.invoke(cli, ["upgrade", "apply"])
    assert result.exit_code == 0, result.output
    assert "backup:" in result.output
    assert ".backups/" in result.output.replace(os.sep, "/")
    assert "roll back with `cataforge upgrade rollback`" in result.output

    backups_root = project / ".cataforge" / ".backups"
    assert backups_root.is_dir()
    assert any(p.is_dir() for p in backups_root.iterdir())


def test_upgrade_apply_hints_deploy_when_deploy_state_exists(
    runner: CliRunner, project: Path
) -> None:
    """Once a project has deployed, re-running `upgrade apply` must remind
    the user to re-deploy — scaffold refresh doesn't touch `.claude/`
    artifacts, and stale settings.json silently drops hook wiring."""
    (project / ".cataforge" / ".deploy-state").write_text(
        '{"platform": "claude-code"}\n', encoding="utf-8"
    )

    result = runner.invoke(cli, ["upgrade", "apply"])
    assert result.exit_code == 0, result.output
    assert "`cataforge deploy`" in result.output
    assert "platform deliverables" in result.output


def test_upgrade_apply_no_deploy_hint_when_never_deployed(
    runner: CliRunner, project: Path
) -> None:
    """Fresh projects (pre-deploy) must not see the re-deploy nag."""
    assert not (project / ".cataforge" / ".deploy-state").exists()

    result = runner.invoke(cli, ["upgrade", "apply"])
    assert result.exit_code == 0, result.output
    assert "`cataforge deploy`" not in result.output


def test_rollback_list_with_no_backups_exits_nonzero(
    runner: CliRunner, project: Path
) -> None:
    result = runner.invoke(cli, ["upgrade", "rollback"])
    assert result.exit_code == 1
    assert "(none" in result.output


def test_rollback_restores_user_edits(
    runner: CliRunner, project: Path
) -> None:
    target_agent = next((project / ".cataforge" / "agents").rglob("AGENT.md"))
    target_agent.write_text("# my agent v1\n", encoding="utf-8")

    apply_result = runner.invoke(cli, ["upgrade", "apply"])
    assert apply_result.exit_code == 0, apply_result.output
    # Post-apply, the custom edit is gone.
    assert "# my agent v1" not in target_agent.read_text(encoding="utf-8")

    rollback = runner.invoke(cli, ["upgrade", "rollback", "--yes"])
    assert rollback.exit_code == 0, rollback.output
    assert "Rollback complete" in rollback.output or "rollback complete" in rollback.output
    # The user edit is back.
    assert "# my agent v1" in target_agent.read_text(encoding="utf-8")


def test_rollback_from_unknown_snapshot_errors(
    runner: CliRunner, project: Path
) -> None:
    runner.invoke(cli, ["upgrade", "apply"])
    result = runner.invoke(
        cli, ["upgrade", "rollback", "--from", "nonexistent-ts", "--yes"]
    )
    assert result.exit_code != 0
    assert "No snapshot matches" in (result.output)


def test_breaking_detection_on_matching_range(tmp_path: Path, monkeypatch) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "## [0.2.0] — 2026-05-01\n\n"
        "### BREAKING\n\n"
        "- framework.json renamed to project.json\n\n"
        "## [0.1.9] — 2026-04-28\n\n"
        "### Added\n\n"
        "- nothing breaking\n\n"
        "## [0.1.8] — 2026-04-24\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    entries = _find_breaking_entries("0.1.8", "0.2.0")
    assert entries == [("0.2.0", "framework.json renamed to project.json")]


def test_breaking_detection_skips_out_of_range(
    tmp_path: Path, monkeypatch
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "## [0.3.0]\n### BREAKING\n- big change\n\n"
        "## [0.2.0]\n### Added\n- feature\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    # installed=0.2.0 skips the 0.3.0 BREAKING since it's above the range.
    assert _find_breaking_entries("0.1.0", "0.2.0") == []


def test_breaking_detection_no_changelog_returns_empty(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert _find_breaking_entries("0.1.0", "0.2.0") == []
