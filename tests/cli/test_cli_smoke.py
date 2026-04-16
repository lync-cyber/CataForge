"""CLI smoke / integration tests — invoke commands via click's CliRunner.

Covers end-to-end wiring: `cataforge setup --no-deploy` scaffolds a fresh
project, subcommands (`skill list`, `mcp list`, `plugin list`, `hook list`,
`doctor`) run to completion, and stub commands (`upgrade`, `hook test`,
`plugin install`) surface the friendly exit-code-2 message.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli.main import cli
from cataforge.cli.stubs import STUB_EXIT_CODE


@pytest.fixture
def fresh_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tmp project with the bundled .cataforge/ scaffold copied in."""
    from cataforge.core.scaffold import copy_scaffold_to

    copy_scaffold_to(tmp_path / ".cataforge", force=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _invoke(*args: str) -> "object":
    runner = CliRunner()
    return runner.invoke(cli, list(args), catch_exceptions=False)


class TestSetupCommand:
    def test_setup_no_deploy_scaffolds_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = _invoke("setup", "--no-deploy")
        assert result.exit_code == 0, result.output
        assert (tmp_path / ".cataforge" / "framework.json").is_file()
        assert (tmp_path / ".cataforge" / "hooks" / "hooks.yaml").is_file()
        assert "Setup complete" in result.output

    def test_setup_platform_does_not_deploy_by_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: `setup --platform X` must be scaffold-only by default.

        Before the fix, `setup --platform claude-code` silently triggered a
        full deploy, muddling the five-step pipeline in the manual
        verification guide.  Now deploy requires explicit opt-in.
        """
        monkeypatch.chdir(tmp_path)
        result = _invoke("setup", "--platform", "claude-code")
        assert result.exit_code == 0, result.output
        assert not (tmp_path / "CLAUDE.md").exists()
        assert not (tmp_path / ".claude" / "agents").exists()
        assert not (tmp_path / ".claude" / "settings.json").exists()
        assert "Platform set to: claude-code" in result.output
        assert "cataforge deploy" in result.output  # guidance banner

    def test_setup_platform_with_deploy_flag_writes_artifacts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Opt-in --deploy still chains scaffold + deploy in a single call."""
        monkeypatch.chdir(tmp_path)
        result = _invoke("setup", "--platform", "claude-code", "--deploy")
        assert result.exit_code == 0, result.output
        assert (tmp_path / "CLAUDE.md").is_file()
        assert (tmp_path / ".claude" / "settings.json").is_file()

    def test_setup_check_only(self, fresh_project: Path) -> None:
        result = _invoke("setup", "--check-only")
        assert result.exit_code == 0, result.output
        assert "framework.json" in result.output
        assert "hooks.yaml" in result.output


class TestListCommands:
    def test_skill_list_shows_builtins(self, fresh_project: Path) -> None:
        result = _invoke("skill", "list")
        assert result.exit_code == 0, result.output
        # At least one built-in skill should render.
        assert "code-review" in result.output or "code_review" in result.output

    def test_mcp_list_runs(self, fresh_project: Path) -> None:
        result = _invoke("mcp", "list")
        assert result.exit_code == 0, result.output

    def test_plugin_list_empty_project(self, fresh_project: Path) -> None:
        result = _invoke("plugin", "list")
        assert result.exit_code == 0, result.output

    def test_hook_list_runs(self, fresh_project: Path) -> None:
        result = _invoke("hook", "list")
        assert result.exit_code == 0, result.output


class TestStubCommands:
    """Commands on the roadmap should fail fast with a clear message."""

    def test_upgrade_check_reports_versions(self, fresh_project: Path) -> None:
        """check is no longer a stub — it compares installed vs scaffold."""
        result = _invoke("upgrade", "check")
        assert result.exit_code == 0, result.output
        assert "Scaffold version" in result.output
        assert "Installed package" in result.output

    def test_upgrade_apply_dry_run(self, fresh_project: Path) -> None:
        result = _invoke("upgrade", "apply", "--dry-run")
        assert result.exit_code == 0, result.output
        assert "Would refresh" in result.output

    def test_upgrade_verify_delegates_to_doctor(self, fresh_project: Path) -> None:
        result = _invoke("upgrade", "verify")
        # verify is an alias for doctor — exit code depends on checks, but the
        # banner confirms delegation happened.
        assert "CataForge Doctor" in result.output

    def test_hook_test_rejects_unknown_hook(self, fresh_project: Path) -> None:
        """`hook test` is no longer a stub — it runs the named script.

        See tests/cli/test_hook_cmd.py for the happy-path coverage; this
        smoke-test locks in the error path for unknown hook names.
        """
        result = _invoke("hook", "test", "pre-commit")
        assert result.exit_code == 1
        assert "not declared" in result.output.lower() or "no hook" in result.output.lower()

    def test_plugin_install_is_stub(self, fresh_project: Path) -> None:
        result = _invoke("plugin", "install", "example")
        assert result.exit_code == STUB_EXIT_CODE
        # Install-stub points users at the real installation path.
        assert "pip" in result.output or "pip" in (result.stderr or "")

    def test_plugin_remove_is_stub(self, fresh_project: Path) -> None:
        result = _invoke("plugin", "remove", "example")
        assert result.exit_code == STUB_EXIT_CODE


class TestVersion:
    def test_version_flag(self) -> None:
        result = _invoke("--version")
        assert result.exit_code == 0
        assert "cataforge" in result.output.lower()
