"""Doctor must be a real integrity gate, not a passive reporter.

Pinned bug: ``cataforge doctor`` exited 0 even when the directories it
listed as ``[absent]`` truly were absent. Symptoms users reported:

* Deleting ``.claude/skills/`` post-deploy did not fail doctor.
* Deleting ``.cataforge/skills/`` (a required source asset) did not
  fail doctor — only the migration-checks block contributed to the
  exit code.

Post-fix contract:

* ``.cataforge/{agents,skills,rules,hooks,platforms}`` are required
  source-asset directories — missing → ``doctor`` exits non-zero.
* When ``.deploy-state`` records a platform, every owned deployed
  directory for that platform must exist (or, if it's a link, must
  resolve). Missing or dangling → ``doctor`` exits non-zero.
* The final line of output must be a ``Summary:`` row that explains
  what passed / failed so the user does not have to scan 13 sections.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.interface.cli.doctor_cmd import doctor_command


def _minimal_project(tmp_path: Path) -> Path:
    cf = tmp_path / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "runtime_api_version": "1.0",
                "migration_checks": [],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _populate_source_dirs(root: Path, *names: str) -> None:
    """Create ``.cataforge/<name>/`` for each name so existence checks pass.

    Tests use this in addition to :func:`populate_required_source_assets`
    when they need to model "all required dirs present" without writing
    the canonical hooks.yaml. Kept as a thin wrapper for test readability.
    """
    for name in names:
        (root / ".cataforge" / name).mkdir(parents=True, exist_ok=True)


def _write_deploy_state(root: Path, platform: str) -> None:
    (root / ".cataforge" / ".deploy-state").write_text(
        json.dumps({"platform": platform}), encoding="utf-8"
    )


def _make_skill(skills_dir: Path, name: str) -> Path:
    skill = skills_dir / name
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n# {name}\n",
        encoding="utf-8",
    )
    return skill


def _link_skill(source_skill: Path, deployed_skills_dir: Path) -> Path:
    """Mirror what ``cataforge deploy`` would create for one skill."""
    deployed_skills_dir.mkdir(parents=True, exist_ok=True)
    target = deployed_skills_dir / source_skill.name
    try:
        os.symlink(str(source_skill), str(target), target_is_directory=True)
    except (OSError, NotImplementedError):
        if os.name == "nt":
            import subprocess

            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(target), str(source_skill)],
                check=True,
                capture_output=True,
            )
        else:
            raise
    return target


class TestDoctorAsIntegrityGate:
    def test_doctor_fails_when_cataforge_skills_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _minimal_project(tmp_path)
        _populate_source_dirs(root, "agents", "rules", "hooks", "platforms")
        (root / ".cataforge" / "hooks" / "hooks.yaml").write_text(
            "version: 1\n", encoding="utf-8"
        )
        # skills/ deliberately missing
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code != 0, result.output
        assert ".cataforge/skills" in result.output
        # The output must explain the failure, not just say "MISSING".
        assert "FAIL" in result.output

    def test_doctor_fails_when_deployed_skills_dir_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Deploy-state recorded → owned dirs must exist."""
        root = _minimal_project(tmp_path)
        _populate_source_dirs(
            root, "agents", "skills", "rules", "hooks", "platforms"
        )
        (root / ".cataforge" / "hooks" / "hooks.yaml").write_text(
            "version: 1\n", encoding="utf-8"
        )
        _make_skill(root / ".cataforge" / "skills", "alpha")
        _write_deploy_state(root, "claude-code")
        # No .claude/skills/ created — owned but missing.
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code != 0, result.output
        assert ".claude/skills" in result.output
        # Remediation hint must point the user at deploy.
        assert "cataforge deploy" in result.output

    def test_doctor_fails_on_dangling_skill_link(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A symlink/junction whose source disappeared must FAIL with the
        skill name in the output."""
        root = _minimal_project(tmp_path)
        _populate_source_dirs(
            root, "agents", "skills", "rules", "hooks", "platforms"
        )
        (root / ".cataforge" / "hooks" / "hooks.yaml").write_text(
            "version: 1\n", encoding="utf-8"
        )
        src_skill = _make_skill(root / ".cataforge" / "skills", "alpha")
        deployed_skills = root / ".claude" / "skills"
        _link_skill(src_skill, deployed_skills)
        _write_deploy_state(root, "claude-code")
        # Now wipe the source — the link is dangling.
        shutil.rmtree(src_skill)
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code != 0, result.output
        # Must call out the broken link by name.
        assert "alpha" in result.output
        # Must use the word "dangling" or "broken" so the user knows what
        # kind of failure this is.
        assert "dangling" in result.output.lower() or "broken" in result.output.lower()

    def test_doctor_passes_clean_deployed_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sanity guard: a well-formed project must still exit 0 after the
        stricter checks land."""
        root = _minimal_project(tmp_path)
        _populate_source_dirs(
            root, "agents", "skills", "rules", "hooks", "platforms"
        )
        (root / ".cataforge" / "hooks" / "hooks.yaml").write_text(
            "version: 1\n", encoding="utf-8"
        )
        src_skill = _make_skill(root / ".cataforge" / "skills", "alpha")
        _link_skill(src_skill, root / ".claude" / "skills")
        # ``.claude/settings.json`` is in the owned provenance map — create
        # it so the new integrity check doesn't flag it.
        (root / ".claude").mkdir(exist_ok=True)
        (root / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")
        (root / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
        (root / ".claude" / "rules").mkdir(parents=True, exist_ok=True)
        (root / ".claude" / "commands").mkdir(parents=True, exist_ok=True)
        _write_deploy_state(root, "claude-code")
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code == 0, result.output

    def test_doctor_prints_summary_line(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Final ``Summary:`` row makes the verdict scannable."""
        root = _minimal_project(tmp_path)
        _populate_source_dirs(
            root, "agents", "skills", "rules", "hooks", "platforms"
        )
        (root / ".cataforge" / "hooks" / "hooks.yaml").write_text(
            "version: 1\n", encoding="utf-8"
        )
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        # Regardless of pass/fail the summary line must be present so users
        # can tell at a glance what happened.
        assert "Summary:" in result.output, result.output

    def test_doctor_summary_reports_failed_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Summary line on a failing run must include the failure count."""
        root = _minimal_project(tmp_path)
        # skills/ missing → at least one failure expected.
        _populate_source_dirs(root, "agents", "rules", "hooks", "platforms")
        (root / ".cataforge" / "hooks" / "hooks.yaml").write_text(
            "version: 1\n", encoding="utf-8"
        )
        monkeypatch.chdir(root)

        result = CliRunner().invoke(doctor_command, [])
        assert result.exit_code != 0
        # e.g. "Summary: 12 passed, 1 failed" — the digit before "failed"
        # must be >= 1.
        import re

        m = re.search(r"Summary:.*?(\d+)\s+failed", result.output)
        assert m and int(m.group(1)) >= 1, result.output
