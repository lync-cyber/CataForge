"""Tests for `cataforge doctor` deployment-provenance reporting.

``doctor`` reads the per-platform deploy manifests and prints a
"Deployment provenance" section counting how many manifest-owned paths
are present for each deployed platform. It also flags a stale Cursor
`.claude/rules` mirror when the mirror flag is off.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cataforge.interface.cli.doctor_cmd import doctor_command


def _minimal_project(tmp_path: Path, *, migration_checks: list[dict] | None = None) -> Path:
    from tests.cli.conftest import populate_required_source_assets

    cf = tmp_path / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "runtime_api_version": "1.0",
                "migration_checks": migration_checks or [],
            }
        ),
        encoding="utf-8",
    )
    populate_required_source_assets(cf)
    return tmp_path


def _write_platform_record(root: Path, platform: str, owned: list[str]) -> None:
    """Write the per-platform deploy record a real deploy would leave behind."""
    d = root / ".cataforge" / "state" / "deploy" / platform
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(
        json.dumps({"manifest_version": 1, "platform": platform, "owned_paths": owned}),
        encoding="utf-8",
    )
    (d / "state.json").write_text(
        json.dumps({"platform": platform, "package_version": "0.1.0"}), encoding="utf-8"
    )


def _write_cursor_profile(root: Path, *, mirror: bool) -> None:
    profile_dir = root / ".cataforge" / "platforms" / "cursor"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "profile.yaml").write_text(
        f"platform_id: cursor\nrules:\n  cross_platform_mirror: {str(mirror).lower()}\n",
        encoding="utf-8",
    )


def _deployed_cursor(root: Path) -> None:
    """Cursor deploy record whose single owned path exists on disk."""
    owned = root / ".cursor" / "rules" / "owned.mdc"
    owned.parent.mkdir(parents=True, exist_ok=True)
    owned.write_text("body\n", encoding="utf-8")
    _write_platform_record(root, "cursor", [".cursor/rules/owned.mdc"])


class TestDoctorProvenance:
    def test_no_deploy_state_shows_hint(self, tmp_path: Path, monkeypatch) -> None:
        """Fresh project: provenance section guides the user to run deploy."""
        root = _minimal_project(tmp_path)
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code == 0, result.output
        assert "Deployment provenance:" in result.output
        assert "no deploy has been run yet" in result.output

    def test_claude_code_deploy_lists_owned_paths(self, tmp_path: Path, monkeypatch) -> None:
        """After a claude-code deploy, doctor counts present vs recorded
        owned paths; the deploy-integrity gate FAILs the run for each
        missing artefact with a per-platform remediation hint."""
        root = _minimal_project(tmp_path)
        _write_platform_record(
            root, "claude-code", [".claude/agents/orchestrator.md", ".claude/settings.json"]
        )
        agent = root / ".claude" / "agents" / "orchestrator.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("body\n", encoding="utf-8")
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code != 0, result.output
        assert "claude-code: 1/2 owned path(s) present (CataForge-managed)" in result.output
        assert (
            "FAIL claude-code: .claude/settings.json missing — "
            "re-run `cataforge deploy --platform claude-code`"
        ) in result.output

    def test_cursor_deploy_flags_stale_claude_rules_when_mirror_off(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Cursor deploy record + mirror=false + `.claude/rules` present
        (and no claude-code deploy record) → NOTE printed."""
        root = _minimal_project(tmp_path)
        _deployed_cursor(root)
        _write_cursor_profile(root, mirror=False)
        stale = root / ".claude" / "rules"
        stale.mkdir(parents=True)
        (stale / "COMMON-RULES.md").write_text("# stale\n", encoding="utf-8")
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code == 0, result.output
        assert "cursor: 1/1 owned path(s) present (CataForge-managed)" in result.output
        assert "NOTE: .claude/rules exists" in result.output
        assert "cross_platform_mirror" in result.output

    def test_cursor_deploy_no_note_when_mirror_on(self, tmp_path: Path, monkeypatch) -> None:
        """Mirror opt-in: `.claude/rules` is expected, so no stale-note fires."""
        root = _minimal_project(tmp_path)
        _deployed_cursor(root)
        _write_cursor_profile(root, mirror=True)
        stale = root / ".claude" / "rules"
        stale.mkdir(parents=True)
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code == 0, result.output
        assert "NOTE: .claude/rules exists" not in result.output

    def test_cursor_deploy_no_note_when_mirror_absent(self, tmp_path: Path, monkeypatch) -> None:
        """No stale `.claude/rules` on disk → no stale-note."""
        root = _minimal_project(tmp_path)
        _deployed_cursor(root)
        _write_cursor_profile(root, mirror=False)
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code == 0, result.output
        assert "NOTE: .claude/rules exists" not in result.output

    def test_unregistered_platform_reported_from_manifest(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A deploy record for a platform without a built-in profile is
        still reported straight from its own manifest."""
        root = _minimal_project(tmp_path)
        _write_platform_record(root, "some-new-platform", [])
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code == 0, result.output
        assert "some-new-platform: 0/0 owned path(s) present (CataForge-managed)" in result.output

    def test_malformed_legacy_deploy_state_treated_as_undeployed(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A corrupt legacy .deploy-state yields no deploy record: doctor
        reports the pre-deploy hint instead of crashing."""
        root = _minimal_project(tmp_path)
        (root / ".cataforge" / ".deploy-state").write_text("{not-json", encoding="utf-8")
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code == 0, result.output
        assert "no deploy has been run yet" in result.output
