"""Tests for `cataforge doctor` deployment-provenance reporting.

Post-M8 behaviour: ``doctor`` reads ``.cataforge/.deploy-state`` and prints a
"Deployment provenance" section listing which platform-specific directories
CataForge owns after the last deploy.  This turns the previously-invisible
"what did deploy actually write?" question into a concrete punch-list and
flags stale Cursor `.claude/rules` mirrors when the mirror flag is off.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cataforge.cli.doctor_cmd import doctor_command


def _minimal_project(tmp_path: Path, *, migration_checks: list[dict] | None = None) -> Path:
    cf = tmp_path / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps(
            {"version": "0.1.0", "migration_checks": migration_checks or []}
        ),
        encoding="utf-8",
    )
    return tmp_path


def _write_deploy_state(root: Path, platform: str) -> None:
    (root / ".cataforge" / ".deploy-state").write_text(
        json.dumps({"platform": platform}), encoding="utf-8"
    )


def _write_cursor_profile(root: Path, *, mirror: bool) -> None:
    profile_dir = root / ".cataforge" / "platforms" / "cursor"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "profile.yaml").write_text(
        f"platform_id: cursor\nrules:\n  cross_platform_mirror: {str(mirror).lower()}\n",
        encoding="utf-8",
    )


class TestDoctorProvenance:
    def test_no_deploy_state_shows_hint(self, tmp_path: Path, monkeypatch) -> None:
        """Fresh project: provenance section guides the user to run deploy."""
        root = _minimal_project(tmp_path)
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code == 0, result.output
        assert "Deployment provenance:" in result.output
        assert "no deploy has been run yet" in result.output

    def test_claude_code_deploy_lists_owned_dirs(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """After a claude-code deploy, doctor lists the owned namespace."""
        root = _minimal_project(tmp_path)
        _write_deploy_state(root, "claude-code")
        # Create one of the owned dirs so we can verify present vs absent.
        (root / ".claude" / "agents").mkdir(parents=True)
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code == 0, result.output
        assert "Last deploy target: claude-code" in result.output
        assert "[present] .claude/agents" in result.output
        assert "[absent] .claude/settings.json" in result.output

    def test_cursor_deploy_flags_stale_claude_rules_when_mirror_off(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Cursor deploy + mirror=false + `.claude/rules` present → NOTE printed."""
        root = _minimal_project(tmp_path)
        _write_deploy_state(root, "cursor")
        _write_cursor_profile(root, mirror=False)
        # Simulate a stale artifact from a pre-M5 deploy.
        stale = root / ".claude" / "rules"
        stale.mkdir(parents=True)
        (stale / "COMMON-RULES.md").write_text("# stale\n", encoding="utf-8")
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code == 0, result.output
        assert "Last deploy target: cursor" in result.output
        assert "NOTE: .claude/rules exists" in result.output
        assert "cross_platform_mirror" in result.output

    def test_cursor_deploy_no_note_when_mirror_on(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Mirror opt-in: `.claude/rules` is expected, so no stale-note fires."""
        root = _minimal_project(tmp_path)
        _write_deploy_state(root, "cursor")
        _write_cursor_profile(root, mirror=True)
        stale = root / ".claude" / "rules"
        stale.mkdir(parents=True)
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code == 0, result.output
        assert "NOTE: .claude/rules exists" not in result.output

    def test_cursor_deploy_no_note_when_mirror_absent(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """No stale `.claude/rules` on disk → no stale-note."""
        root = _minimal_project(tmp_path)
        _write_deploy_state(root, "cursor")
        _write_cursor_profile(root, mirror=False)
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code == 0, result.output
        assert "NOTE: .claude/rules exists" not in result.output

    def test_unknown_platform_reports_missing_map(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Deploy-state referencing an unmapped platform degrades gracefully."""
        root = _minimal_project(tmp_path)
        _write_deploy_state(root, "some-new-platform")
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code == 0, result.output
        assert "no provenance map declared" in result.output

    def test_malformed_deploy_state_reported(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Corrupt .deploy-state: surface the parse failure, don't crash doctor."""
        root = _minimal_project(tmp_path)
        (root / ".cataforge" / ".deploy-state").write_text(
            "{not-json", encoding="utf-8"
        )
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code == 0, result.output
        assert "could not parse" in result.output
