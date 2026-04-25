"""Regression: doctor must exit non-zero when migration checks fail."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cataforge.cli.doctor_cmd import doctor_command


def _minimal_project(tmp_path: Path, checks: list[dict]) -> Path:
    cf = tmp_path / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "migration_checks": checks}),
        encoding="utf-8",
    )
    return tmp_path


def test_doctor_passes_with_no_checks(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path, [])
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 0


def test_doctor_fails_when_migration_check_fails(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(
        tmp_path,
        [
            {
                "id": "test-must-exist",
                "type": "file_must_exist",
                "path": "nonexistent.md",
            }
        ],
    )
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 1
    assert "FAIL test-must-exist" in result.output


def test_doctor_passes_when_checks_satisfied(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(
        tmp_path,
        [
            {
                "id": "test-must-exist",
                "type": "file_must_exist",
                "path": ".cataforge/framework.json",
            }
        ],
    )
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 0


def test_doctor_skips_requires_deploy_check_before_first_deploy(
    tmp_path: Path, monkeypatch
) -> None:
    """Checks marked ``requires_deploy`` must SKIP (not FAIL) pre-deploy.

    Regression guard: before this fix, a fresh-install flow (install package,
    then ``cataforge doctor``) exited 1 because ``.claude/settings.json``
    does not exist until the first ``cataforge deploy``.
    """
    root = _minimal_project(
        tmp_path,
        [
            {
                "id": "mc-test-requires-deploy",
                "type": "file_must_contain",
                "path": ".claude/settings.json",
                "patterns": ["anything"],
                "requires_deploy": True,
            }
        ],
    )
    monkeypatch.chdir(root)

    # No .deploy-state yet → SKIP, exit 0.
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 0, result.output
    assert "SKIP mc-test-requires-deploy" in result.output


def test_doctor_fails_on_missing_protocol_script(
    tmp_path: Path, monkeypatch
) -> None:
    """Regression: ``doctor`` must flag markdown that invokes a ``python
    .cataforge/scripts/...`` path that does not exist on disk. This is the
    class of bug that let ``event_logger.py`` go missing unnoticed for months.
    """
    root = _minimal_project(tmp_path, [])
    agents_dir = root / ".cataforge" / "agents" / "phantom"
    agents_dir.mkdir(parents=True)
    (agents_dir / "AGENT.md").write_text(
        "See `python .cataforge/scripts/framework/does_not_exist.py --flag`.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 1, result.output
    assert ".cataforge/scripts/framework/does_not_exist.py" in result.output
    assert ".cataforge/agents/phantom/AGENT.md:1" in result.output


def test_doctor_flags_missing_skill_subdir_script(
    tmp_path: Path, monkeypatch
) -> None:
    """Regression for the dep-analysis class of bug: SKILL.md docs that
    instruct ``python .cataforge/skills/<id>/scripts/<x>.py`` must be flagged
    when ``scripts/`` doesn't exist on disk. The original regex only
    matched ``.cataforge/scripts/...`` and let this slip through."""
    root = _minimal_project(tmp_path, [])
    skill_dir = root / ".cataforge" / "skills" / "phantom"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "Run `python .cataforge/skills/phantom/scripts/runner.py --flag`.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 1, result.output
    assert ".cataforge/skills/phantom/scripts/runner.py" in result.output


def test_doctor_flags_missing_integrations_script(
    tmp_path: Path, monkeypatch
) -> None:
    """Regression for the Penpot class of bug: docs that instruct
    ``python .cataforge/integrations/<x>/<y>.py`` must be flagged when the
    on-disk path is missing — those scripts now live inside the cataforge
    package and are reachable only via the CLI."""
    root = _minimal_project(tmp_path, [])
    skill_dir = root / ".cataforge" / "skills" / "phantom"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "Run `python .cataforge/integrations/foo/setup.py ensure`.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 1, result.output
    assert ".cataforge/integrations/foo/setup.py" in result.output


def test_doctor_passes_when_referenced_script_exists(
    tmp_path: Path, monkeypatch
) -> None:
    """A reference that resolves should not count toward doctor's exit code."""
    root = _minimal_project(tmp_path, [])
    scripts_dir = root / ".cataforge" / "scripts" / "framework"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "real_script.py").write_text("# real\n", encoding="utf-8")
    agents_dir = root / ".cataforge" / "agents" / "phantom"
    agents_dir.mkdir(parents=True)
    (agents_dir / "AGENT.md").write_text(
        "Run `python .cataforge/scripts/framework/real_script.py`.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 0, result.output
    assert "1/1 scripts present" in result.output
    assert "FAIL" not in result.output


def test_doctor_runs_requires_deploy_check_after_deploy(
    tmp_path: Path, monkeypatch
) -> None:
    """Once .deploy-state exists, requires_deploy checks are enforced."""
    root = _minimal_project(
        tmp_path,
        [
            {
                "id": "mc-test-requires-deploy",
                "type": "file_must_exist",
                "path": ".claude/settings.json",
                "requires_deploy": True,
            }
        ],
    )
    (root / ".cataforge" / ".deploy-state").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(root)

    result = CliRunner().invoke(doctor_command, [])
    assert result.exit_code == 1, result.output
    assert "FAIL mc-test-requires-deploy" in result.output
