"""doctor must flag when review skills' Layer 1 scripts are unreachable.

Regression for the shadow-bug root cause: a project-level SKILL.md with
no scripts/ used to silently shadow the builtin, leaving
``cataforge skill run <id>`` unable to dispatch — Layer 1 never ran and
no review report was generated. The fix merges builtin scripts when the
project override is script-less; this test ensures doctor surfaces the
case when the merge can't happen (e.g. the builtin really is absent).
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cataforge.cli.doctor_cmd import doctor_command


def _project(tmp_path: Path) -> Path:
    cf = tmp_path / ".cataforge"
    (cf / "hooks").mkdir(parents=True)
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )
    return tmp_path


def test_doctor_passes_for_default_builtin_skills(tmp_path: Path, monkeypatch) -> None:
    """With no project override, every builtin must be reachable."""
    from cataforge.skill.loader import SkillLoader

    root = _project(tmp_path)
    monkeypatch.chdir(root)
    builtin_count = len(SkillLoader(project_root=root)._scan_builtins())
    result = CliRunner().invoke(doctor_command, [])
    assert "Built-in skill reachability" in result.output
    assert (
        f"{builtin_count}/{builtin_count} built-in skills have an executable entry point"
        in result.output
    )


def test_doctor_passes_when_project_override_merges_builtin(
    tmp_path: Path, monkeypatch
) -> None:
    """A project-level SKILL.md with no scripts/ must still resolve via
    the loader's builtin-fallback merge — covers code-review (review skill)
    and task-dep-analysis (formerly dep-analysis, the post-fix regression
    target — renamed in v0.1.15)."""
    from cataforge.skill.loader import SkillLoader

    root = _project(tmp_path)
    for skill_id in ("code-review", "task-dep-analysis"):
        skill_dir = root / ".cataforge" / "skills" / skill_id
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {skill_id}\ndescription: override\n---\nbody\n",
            encoding="utf-8",
        )
    monkeypatch.chdir(root)
    builtin_count = len(SkillLoader(project_root=root)._scan_builtins())
    result = CliRunner().invoke(doctor_command, [])
    assert (
        f"{builtin_count}/{builtin_count} built-in skills have an executable entry point"
        in result.output
    )
