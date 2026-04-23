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

    def test_setup_dry_run_makes_no_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`setup --dry-run --platform X` previews without touching disk."""
        monkeypatch.chdir(tmp_path)
        result = _invoke("setup", "--dry-run", "--platform", "cursor")
        assert result.exit_code == 0, result.output
        assert not (tmp_path / ".cataforge").exists()
        assert "would scaffold" in result.output
        assert "would set" in result.output or "would patch" in result.output
        assert "Dry-run complete" in result.output

    def test_setup_dry_run_on_existing_project_reports_diff(
        self, fresh_project: Path
    ) -> None:
        """Existing project: dry-run shows the exact runtime.platform patch."""
        result = _invoke("setup", "--dry-run", "--platform", "cursor")
        assert result.exit_code == 0, result.output
        assert "would patch framework.json" in result.output
        assert "runtime.platform" in result.output
        assert "'claude-code' → 'cursor'" in result.output

    def test_setup_show_diff_prints_single_field(self, fresh_project: Path) -> None:
        """`--show-diff` surfaces the one field that actually changes."""
        result = _invoke("setup", "--platform", "cursor", "--show-diff")
        assert result.exit_code == 0, result.output
        assert "framework.json diff" in result.output
        assert "runtime.platform" in result.output
        assert "framework.json modified only at runtime.platform" in result.output

    def test_setup_platform_preserves_framework_json_fields(
        self, fresh_project: Path
    ) -> None:
        """End-to-end M1 regression: CLI setup --platform doesn't lose fields."""
        import json as _json

        fw_path = fresh_project / ".cataforge" / "framework.json"
        before = _json.loads(fw_path.read_text(encoding="utf-8"))

        # Hand-edit framework.json the way a real user might (custom upgrade
        # source fields the bundled Pydantic schema previously dropped).
        before["upgrade"]["source"]["token_env"] = "MY_TOKEN"
        before["upgrade"]["state"]["last_commit"] = "deadbeef"
        before["upgrade"]["state"]["last_upgrade_date"] = "2026-04-01"
        fw_path.write_text(_json.dumps(before, indent=2), encoding="utf-8")

        result = _invoke("setup", "--platform", "cursor")
        assert result.exit_code == 0, result.output

        after = _json.loads(fw_path.read_text(encoding="utf-8"))
        assert after["upgrade"]["source"]["token_env"] == "MY_TOKEN"
        assert after["upgrade"]["state"]["last_commit"] == "deadbeef"
        assert after["upgrade"]["state"]["last_upgrade_date"] == "2026-04-01"
        # Only runtime.platform should have changed.
        before["runtime"]["platform"] = "cursor"
        assert after == before


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


class TestDeployErrors:
    """Deploy must fail gracefully when scaffold is missing."""

    def test_deploy_without_scaffold_is_friendly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No .cataforge/ anywhere — deploy should hint at setup, not crash.

        Before the fix, users hit a raw FileNotFoundError traceback deep
        inside registry.load_profile. Now the CLI points to `cataforge setup`.
        """
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "--platform", "claude-code"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output
        assert "cataforge setup" in result.output
        assert ".cataforge" in result.output

    def test_deploy_with_missing_profile_is_friendly(
        self, fresh_project: Path
    ) -> None:
        """Scaffold exists but a platform profile is missing — friendly hint."""
        profile = fresh_project / ".cataforge" / "platforms" / "claude-code" / "profile.yaml"
        profile.unlink()
        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "--platform", "claude-code"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output
        assert "profile" in result.output.lower()
        assert "--force-scaffold" in result.output


class TestGlobalFlags:
    """Group-level flags added in the P0-P3 UX pass."""

    def test_verbose_and_quiet_conflict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = _invoke("-v", "-q", "doctor")
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output

    def test_project_dir_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--project-dir must make subcommands operate on the given root
        regardless of cwd. The previous version of this test used a
        ``fresh_project == tmp_path`` fixture and then chdir'd to a subdir
        of it, which falsely passed because ``find_project_root`` walked
        up and happened to find ``.cataforge/`` again. Here we put cwd in
        a sibling directory so the fallback cannot mask a missing override.
        """
        from cataforge.core.scaffold import copy_scaffold_to

        sibling_a = tmp_path / "project-a"
        sibling_b = tmp_path / "project-b"
        sibling_a.mkdir()
        sibling_b.mkdir()
        copy_scaffold_to(sibling_a / ".cataforge", force=False)
        # Note: no scaffold in sibling_b — walk-up from there would never
        # find one, so any success proves the --project-dir flag took
        # effect rather than fallback discovery.
        monkeypatch.chdir(sibling_b)

        result = _invoke("--project-dir", str(sibling_a), "doctor")
        assert result.exit_code == 0, result.output
        # Project root line must point at sibling_a (the override target),
        # never at sibling_b (cwd) or tmp_path (common ancestor).
        root_lines = [l for l in result.output.splitlines() if "Project root:" in l]
        assert root_lines, f"no 'Project root:' line in output:\n{result.output}"
        assert str(sibling_a) in root_lines[0]
        assert str(sibling_b) not in root_lines[0]

    def test_project_dir_override_reaches_agent_list(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression for R-001: agent/skill/mcp/plugin/hook must honour
        --project-dir too, not just deploy/setup/doctor."""
        from cataforge.core.scaffold import copy_scaffold_to

        sibling_a = tmp_path / "with-scaffold"
        sibling_b = tmp_path / "no-scaffold"
        sibling_a.mkdir()
        sibling_b.mkdir()
        copy_scaffold_to(sibling_a / ".cataforge", force=False)
        monkeypatch.chdir(sibling_b)

        # Without --project-dir: the guard would raise NotInitializedError
        # because sibling_b has no .cataforge/.
        result_bare = _invoke("agent", "list")
        assert result_bare.exit_code != 0
        assert "setup" in result_bare.output.lower()

        # With --project-dir: the same command must succeed, proving the
        # override reaches both the @require_initialized guard AND the
        # AgentManager constructor.
        result_overridden = _invoke("--project-dir", str(sibling_a), "agent", "list")
        assert result_overridden.exit_code == 0, result_overridden.output

    def test_top_level_help_has_getting_started(self) -> None:
        result = _invoke("--help")
        assert result.exit_code == 0
        assert "Getting started" in result.output
        assert "cataforge setup" in result.output


class TestDeprecationWarnings:
    def test_deploy_check_alias_warns(self, fresh_project: Path) -> None:
        """Legacy --check keeps working but prints a deprecation line."""
        result = _invoke("deploy", "--check")
        assert result.exit_code == 0, result.output
        assert "[deprecated]" in result.output
        assert "--dry-run" in result.output

    def test_setup_no_deploy_warns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = _invoke("setup", "--no-deploy")
        assert result.exit_code == 0, result.output
        assert "[deprecated]" in result.output
        assert "--no-deploy" in result.output


class TestStubExitCode:
    def test_stub_exit_is_not_2(self) -> None:
        """POSIX exit 2 belongs to Click for usage errors. Stubs must not
        collide with that (would hide real argv mistakes in CI)."""
        from cataforge.cli.stubs import STUB_EXIT_CODE

        assert STUB_EXIT_CODE != 2
        assert STUB_EXIT_CODE == 70  # EX_SOFTWARE


class TestWindowsEncoding:
    """CLI output uses ``—``/``→``/Chinese in several paths. On Windows,
    ``ensure_utf8_stdio()`` (invoked at import time) guarantees UTF-8 on
    stdout/stderr with ``errors='replace'``. These tests pin that down.

    A crash here would typically be ``UnicodeEncodeError: 'charmap'`` and
    would appear as a Python traceback in ``result.output``.
    """

    def test_help_with_em_dash_renders(self) -> None:
        result = _invoke("--help")
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_stub_chinese_renders(self, fresh_project: Path) -> None:
        result = _invoke("plugin", "install", "foo")
        assert "Traceback" not in result.output
        # The stub message contains both Chinese characters and the
        # replacement-free output should include the literal prefix.
        assert "尚未实现" in result.output

    def test_deploy_dry_run_arrow_renders(self, fresh_project: Path) -> None:
        """The deploy command banner uses the em-dash separator; setup's
        dry-run uses the U+2192 arrow for diff output. Both must render."""
        result = _invoke("setup", "--dry-run", "--platform", "cursor")
        assert result.exit_code == 0, result.output
        assert "Traceback" not in result.output


class TestVersion:
    def test_version_flag(self) -> None:
        result = _invoke("--version")
        assert result.exit_code == 0
        assert "cataforge" in result.output.lower()
