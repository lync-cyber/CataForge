"""doctor source-removed orphan detection.

A skill recorded in the deploy manifest whose source under
``.cataforge/skills/`` was removed lingers until the next deploy prunes it.
doctor surfaces it as a WARN — never a FAIL, so the exit code is unchanged.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from cataforge.interface.cli.doctor.deploy_integrity import check_deploy_source_orphans
from cataforge.interface.cli.doctor_cmd import doctor_command


def _cfg(root: Path) -> SimpleNamespace:
    return SimpleNamespace(paths=SimpleNamespace(root=root))


def _make_skill(root: Path, name: str) -> Path:
    d = root / ".cataforge" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n# {name}\n", encoding="utf-8"
    )
    return d


def _write_manifest(root: Path, owned: list[str], platform: str = "claude-code") -> None:
    d = root / ".cataforge" / "state" / "deploy" / platform
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(
        json.dumps({"manifest_version": 1, "platform": platform, "owned_paths": owned}),
        encoding="utf-8",
    )


def test_source_removed_skill_warns_without_gating(tmp_path: Path, capsys) -> None:
    _make_skill(tmp_path, "alpha")
    _write_manifest(tmp_path, [".claude/skills/alpha", ".claude/skills/ghost"])

    rc = check_deploy_source_orphans(_cfg(tmp_path))
    out = capsys.readouterr().out

    assert rc == 0  # source orphans never gate doctor's exit code
    assert "1 deployed skill(s) have no source" in out
    assert "ghost" in out
    assert "WARN" in out
    # The live skill (source still present) must not be flagged.
    assert "alpha" not in out


def test_all_sources_present_is_clean(tmp_path: Path, capsys) -> None:
    _make_skill(tmp_path, "alpha")
    _write_manifest(tmp_path, [".claude/skills/alpha"])

    rc = check_deploy_source_orphans(_cfg(tmp_path))
    out = capsys.readouterr().out

    assert rc == 0
    assert "all have sources" in out


def test_no_manifest_skips(tmp_path: Path, capsys) -> None:
    (tmp_path / ".cataforge").mkdir()
    rc = check_deploy_source_orphans(_cfg(tmp_path))
    out = capsys.readouterr().out
    assert rc == 0
    assert "no deploy manifest" in out


def _link_skill(source_skill: Path, deployed_skills_dir: Path) -> None:
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


def test_full_doctor_exit_code_unchanged_by_ghost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ghost in the manifest produces a WARN but keeps doctor green."""
    cf = tmp_path / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime_api_version": "1.0", "migration_checks": []}),
        encoding="utf-8",
    )
    for name in ("agents", "skills", "rules", "hooks", "platforms"):
        (cf / name).mkdir(parents=True, exist_ok=True)
    (cf / "hooks" / "hooks.yaml").write_text("version: 1\n", encoding="utf-8")
    src_skill = _make_skill(tmp_path, "alpha")
    _link_skill(src_skill, tmp_path / ".claude" / "skills")
    # The ghost's deployed copy lingers on disk while its source is gone —
    # integrity stays green; only the source-orphan WARN fires.
    (tmp_path / ".claude" / "skills" / "ghost").mkdir(parents=True, exist_ok=True)
    _write_manifest(tmp_path, [".claude/skills/alpha", ".claude/skills/ghost"])
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(doctor_command, [])

    assert result.exit_code == 0, result.output
    assert "Deploy source orphans:" in result.output
    assert "ghost" in result.output
