"""Tests for `cataforge bootstrap` — the one-shot setup/upgrade/deploy/doctor
orchestrator.

Each test pins a concrete state (fresh/scaffolded/deployed) and asserts the
plan decides skip vs. run correctly. Skip logic must derive from on-disk
product state alone — there is no `.bootstrap-state` cache — so these tests
also guard against a regression where someone adds such a cache and it
drifts from reality.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def fresh_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Empty directory — no .cataforge/."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def scaffolded_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Project with .cataforge/ already scaffolded. No deploy has run."""
    from cataforge.core.scaffold import copy_scaffold_to

    copy_scaffold_to(tmp_path / ".cataforge", force=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def deployed_project(scaffolded_project: Path) -> Path:
    """Scaffolded project that has also deployed to claude-code."""
    state = scaffolded_project / ".cataforge" / ".deploy-state"
    state.write_text(
        json.dumps({"platform": "claude-code"}) + "\n", encoding="utf-8"
    )
    return scaffolded_project


# ---- dry-run plan assertions ----

class TestDryRunPlan:
    def test_fresh_install_without_platform_blocks(
        self, runner: CliRunner, fresh_project: Path
    ) -> None:
        """Fresh install with no --platform must be a hard error, not a silent
        default — otherwise we'd write .cataforge/ with whichever default we
        happen to pick and lock users into it on first use."""
        result = runner.invoke(cli, ["bootstrap", "--dry-run"])
        assert result.exit_code == 0, result.output  # dry-run prints, doesn't exit
        assert "Fresh install detected" in result.output
        assert "--platform" in result.output

    def test_fresh_install_with_platform_plans_all_steps(
        self, runner: CliRunner, fresh_project: Path
    ) -> None:
        result = runner.invoke(
            cli, ["bootstrap", "--platform", "claude-code", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        # setup runs, upgrade skips (fresh scaffold is by definition current),
        # deploy runs (first deploy), doctor runs.
        assert "setup    run" in result.output
        assert "upgrade  skip" in result.output
        assert "deploy   run" in result.output
        assert "doctor   run" in result.output
        assert "target platform: claude-code" in result.output
        # No files written under dry-run.
        assert not (fresh_project / ".cataforge").exists()

    def test_scaffolded_never_deployed_plans_deploy(
        self, runner: CliRunner, scaffolded_project: Path
    ) -> None:
        result = runner.invoke(cli, ["bootstrap", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "setup    skip" in result.output
        assert "deploy   run" in result.output
        assert "never deployed" in result.output

    def test_fully_bootstrapped_skips_everything_but_doctor(
        self, runner: CliRunner, deployed_project: Path
    ) -> None:
        """The load-bearing idempotency guarantee: re-running a fully set-up
        project only runs doctor."""
        result = runner.invoke(cli, ["bootstrap", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "setup    skip" in result.output
        assert "upgrade  skip" in result.output
        assert "deploy   skip" in result.output
        assert "doctor   run" in result.output

    def test_platform_mismatch_blocks(
        self, runner: CliRunner, deployed_project: Path
    ) -> None:
        """Requesting a different platform than what's recorded must surface
        as an explicit error — bootstrap must NOT silently rewrite
        runtime.platform (that's setup --platform --show-diff's job)."""
        result = runner.invoke(
            cli, ["bootstrap", "--platform", "cursor", "--dry-run"]
        )
        assert result.exit_code == 0, result.output  # dry-run exits 0 even with error
        assert "conflicts with" in result.output
        assert "runtime.platform" in result.output

    def test_platform_changed_triggers_deploy(
        self, runner: CliRunner, scaffolded_project: Path
    ) -> None:
        """If .deploy-state records a different platform than runtime.platform,
        deploy must re-run. (This can happen when the user edits
        runtime.platform via `cataforge setup --platform ...`.)"""
        state = scaffolded_project / ".cataforge" / ".deploy-state"
        state.write_text(
            json.dumps({"platform": "cursor"}) + "\n", encoding="utf-8"
        )
        result = runner.invoke(cli, ["bootstrap", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "deploy   run" in result.output
        assert "platform changed" in result.output

    def test_scaffold_drift_triggers_upgrade_and_deploy(
        self, runner: CliRunner, deployed_project: Path
    ) -> None:
        """A user edit to a scaffold file must both trigger upgrade refresh
        AND force deploy (scaffold change invalidates rendered artefacts)."""
        agent = next(
            (deployed_project / ".cataforge" / "agents").rglob("AGENT.md")
        )
        agent.write_text("user edit\n", encoding="utf-8")

        result = runner.invoke(cli, ["bootstrap", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "upgrade  run" in result.output
        assert "deploy   run" in result.output
        # The reason must mention the scaffold refresh — deploy isn't just
        # re-running because someone felt like it.
        assert (
            "scaffold refreshed" in result.output
            or "scaffold refresh required" in result.output
        )


# ---- execution assertions ----

class TestExecution:
    def test_fresh_install_writes_everything(
        self, runner: CliRunner, fresh_project: Path
    ) -> None:
        """End-to-end: fresh directory → scaffolded + deployed."""
        result = runner.invoke(
            cli,
            ["bootstrap", "--platform", "claude-code", "--yes", "--skip-doctor"],
        )
        assert result.exit_code == 0, result.output

        assert (fresh_project / ".cataforge" / "framework.json").is_file()
        # Platform must be persisted to framework.json.
        fw = json.loads(
            (fresh_project / ".cataforge" / "framework.json").read_text(
                encoding="utf-8"
            )
        )
        assert fw["runtime"]["platform"] == "claude-code"
        # Deploy must have produced .claude/ artefacts.
        assert (fresh_project / ".claude").is_dir()

    def test_idempotent_second_run(
        self, runner: CliRunner, fresh_project: Path
    ) -> None:
        """Running bootstrap twice must not blow up, not re-deploy, and not
        mutate anything the second time (other than running doctor)."""
        first = runner.invoke(
            cli,
            ["bootstrap", "--platform", "claude-code", "--yes", "--skip-doctor"],
        )
        assert first.exit_code == 0, first.output

        second = runner.invoke(cli, ["bootstrap", "--yes", "--skip-doctor"])
        assert second.exit_code == 0, second.output
        assert "setup    skip" in second.output
        assert "deploy   skip" in second.output

    def test_platform_mismatch_fails_during_execution(
        self, runner: CliRunner, deployed_project: Path
    ) -> None:
        """Platform conflict must fail the command, not silently proceed."""
        result = runner.invoke(
            cli,
            [
                "bootstrap",
                "--platform", "cursor",
                "--yes",
                "--skip-doctor",
            ],
        )
        assert result.exit_code != 0
        assert "conflicts with" in result.output

    def test_dry_run_writes_nothing(
        self, runner: CliRunner, fresh_project: Path
    ) -> None:
        """Dry-run must be pure — zero filesystem mutations."""
        before = list(fresh_project.iterdir())
        result = runner.invoke(
            cli,
            ["bootstrap", "--platform", "claude-code", "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        after = list(fresh_project.iterdir())
        assert before == after
