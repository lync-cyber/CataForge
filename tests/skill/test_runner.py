"""Integration tests for SkillLoader + SkillRunner.

Covers discovery of built-in skills, discovery of project-level skills,
project-level precedence over builtins, and the subprocess invocation path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.skill.loader import SkillLoader
from cataforge.skill.runner import SkillRunner


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    return tmp_path


def _write_skill(
    project_root: Path,
    skill_id: str,
    *,
    frontmatter: str = "",
    script_body: str = "print('hello from skill')\n",
) -> Path:
    skill_dir = project_root / ".cataforge" / "skills" / skill_id
    skill_dir.mkdir(parents=True)
    fm = frontmatter or f'---\nname: {skill_id}\ndescription: test skill\n---\n'
    (skill_dir / "SKILL.md").write_text(fm + "\nBody.\n", encoding="utf-8")
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "main.py").write_text(script_body, encoding="utf-8")
    return skill_dir


class TestSkillDiscovery:
    def test_builtins_are_discovered(self, project: Path) -> None:
        loader = SkillLoader(project)
        skills = loader.discover()
        ids = {s.id for s in skills}
        # Built-ins shipped with the package.
        assert "code-review" in ids

    def test_project_skill_discovered(self, project: Path) -> None:
        _write_skill(project, "my-skill")
        loader = SkillLoader(project)
        ids = {s.id for s in loader.discover()}
        assert "my-skill" in ids

    def test_project_skill_overrides_builtin(self, project: Path) -> None:
        _write_skill(project, "code-review")
        loader = SkillLoader(project)
        meta = loader.get_skill("code-review")
        assert meta is not None
        # Project override — not the builtin.
        assert meta.builtin is False

    def test_get_skill_missing_returns_none(self, project: Path) -> None:
        loader = SkillLoader(project)
        assert loader.get_skill("nonexistent-skill-xyz") is None


class TestSkillRunner:
    def test_run_project_skill_succeeds(self, project: Path) -> None:
        _write_skill(
            project,
            "echo-skill",
            script_body=(
                "import os, sys\n"
                "print('ROOT=' + os.environ['CATAFORGE_PROJECT_ROOT'])\n"
                "print('ARGV=' + ','.join(sys.argv[1:]))\n"
            ),
        )
        runner = SkillRunner(project)
        result = runner.run("echo-skill", args=["a", "b"])
        assert result.returncode == 0, result.stderr
        assert f"ROOT={project}" in result.stdout
        assert "ARGV=a,b" in result.stdout

    def test_run_unknown_skill_raises(self, project: Path) -> None:
        runner = SkillRunner(project)
        with pytest.raises(ValueError, match="Skill not found"):
            runner.run("no-such-skill")

    def test_run_skill_without_scripts_raises(self, project: Path) -> None:
        skill_dir = project / ".cataforge" / "skills" / "docs-only"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: docs-only\ndescription: no scripts\n---\nBody.\n",
            encoding="utf-8",
        )
        runner = SkillRunner(project)
        with pytest.raises(ValueError, match="no executable scripts"):
            runner.run("docs-only")

    def test_run_missing_script_name_raises(self, project: Path) -> None:
        _write_skill(project, "named-skill")
        runner = SkillRunner(project)
        with pytest.raises(ValueError, match="not found in skill"):
            runner.run("named-skill", script_name="does-not-exist")

    def test_skill_script_failure_propagates_returncode(self, project: Path) -> None:
        _write_skill(
            project,
            "failing",
            script_body="import sys\nsys.exit(7)\n",
        )
        runner = SkillRunner(project)
        result = runner.run("failing")
        assert result.returncode == 7
