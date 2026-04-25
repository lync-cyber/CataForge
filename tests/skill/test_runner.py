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

    def test_project_skill_without_scripts_borrows_builtin(
        self, project: Path
    ) -> None:
        """When a project SKILL.md exists but has no scripts/, the builtin
        scripts are merged in so `cataforge skill run` stays functional.

        Regression: a bare project-level override silently shadowed the
        builtin, leaving Layer 1 review scripts unreachable. See
        docs/architecture/quality-and-learning.md §2.1.
        """
        skill_dir = project / ".cataforge" / "skills" / "code-review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: code-review\ndescription: override\n---\n"
            "Project-level prose override with no scripts.\n",
            encoding="utf-8",
        )
        loader = SkillLoader(project)
        meta = loader.get_skill("code-review")
        assert meta is not None
        # Builtin scripts were merged in so runner can dispatch.
        assert meta.scripts, "builtin scripts should be merged"
        assert meta.builtin is True
        assert any(s["name"] == "code_lint" for s in meta.scripts)

    def test_project_skill_with_scripts_keeps_its_own(
        self, project: Path
    ) -> None:
        """A project-level SKILL.md that ships its own scripts/ directory
        must not be quietly replaced by the builtin."""
        _write_skill(project, "code-review", script_body="print('local')\n")
        loader = SkillLoader(project)
        meta = loader.get_skill("code-review")
        assert meta is not None
        # Project override — not promoted to builtin.
        assert meta.builtin is False
        assert meta.scripts == [{"name": "main", "entry": "scripts/main.py"}]


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


class TestSkillRunnerEventLog:
    """Layer 1 runs emit state_change records so retrospectives can
    measure the "quality-gate to-work ratio"."""

    def test_review_skill_run_appends_event(self, project: Path) -> None:
        # Override code-review at project level so we can point at a cheap
        # script without shelling out to ruff / eslint. The loader's
        # project-level precedence + runner dispatch makes the effect the
        # same as a builtin call from the event-logging perspective.
        _write_skill(
            project,
            "code-review",
            script_body="import sys; sys.exit(0)\n",
        )
        runner = SkillRunner(project)
        result = runner.run("code-review")
        assert result.returncode == 0

        log = project / "docs" / "EVENT-LOG.jsonl"
        assert log.is_file(), "review skill runs must emit an event"
        import json
        lines = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
        assert any(
            r.get("event") == "state_change"
            and r.get("agent") == "reviewer"
            and r.get("status") == "completed"
            and "code-review" in r.get("detail", "")
            for r in lines
        )

    def test_review_skill_exit1_recorded_as_needs_revision(
        self, project: Path
    ) -> None:
        _write_skill(
            project,
            "sprint-review",
            script_body="import sys; sys.exit(1)\n",
        )
        runner = SkillRunner(project)
        runner.run("sprint-review")

        log = project / "docs" / "EVENT-LOG.jsonl"
        import json
        records = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
        statuses = [r.get("status") for r in records]
        assert "needs_revision" in statuses

    def test_event_log_flag_propagated_to_override(self, project: Path) -> None:
        """A project-level override that ships its own scripts must still
        inherit the event-log flag from the builtin — the "review-ness"
        of code-review/sprint-review/doc-review is intrinsic to the id,
        not the script provider. Regression for the
        frontmatter-driven flag refactor."""
        _write_skill(
            project,
            "doc-review",
            script_body="import sys; sys.exit(0)\n",
        )
        loader = SkillLoader(project)
        meta = loader.get_skill("doc-review")
        assert meta is not None
        assert meta.record_to_event_log, (
            "doc-review override should still record to EVENT-LOG"
        )

    def test_opt_in_via_frontmatter(self, project: Path) -> None:
        """A non-review skill can opt into EVENT-LOG via frontmatter."""
        _write_skill(
            project,
            "custom-gate",
            frontmatter=(
                "---\nname: custom-gate\ndescription: x\n"
                "record-to-event-log: true\n---\n"
            ),
            script_body="import sys; sys.exit(0)\n",
        )
        runner = SkillRunner(project)
        runner.run("custom-gate")
        log = project / "docs" / "EVENT-LOG.jsonl"
        assert log.is_file(), "opt-in skill should emit"

    def test_non_review_skill_run_does_not_emit(self, project: Path) -> None:
        """The event log is narrow by design (see
        docs/architecture/quality-and-learning.md). Non-review skills
        must not widen the stream implicitly."""
        _write_skill(
            project,
            "echo-skill",
            script_body="print('ok')\n",
        )
        runner = SkillRunner(project)
        runner.run("echo-skill")
        assert not (project / "docs" / "EVENT-LOG.jsonl").exists()


class TestSkillRunnerAgentAttribution:
    """Agent attribution: caller may pass agent= explicitly, or set
    CATAFORGE_INVOKING_AGENT in the env, or accept the legacy
    'reviewer' fallback. Regression for hardcoded ``agent="reviewer"``
    that misattributed every review-class run to reviewer regardless
    of who actually invoked it."""

    def _last_record(self, project: Path) -> dict:
        import json
        log = project / "docs" / "EVENT-LOG.jsonl"
        lines = [
            json.loads(ln)
            for ln in log.read_text().splitlines()
            if ln.strip()
        ]
        return lines[-1]

    def test_explicit_agent_param_wins(self, project: Path) -> None:
        _write_skill(
            project,
            "code-review",
            script_body="import sys; sys.exit(0)\n",
        )
        runner = SkillRunner(project)
        runner.run("code-review", agent="orchestrator")
        assert self._last_record(project)["agent"] == "orchestrator"

    def test_env_var_used_when_no_param(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CATAFORGE_INVOKING_AGENT", "tech-lead")
        _write_skill(
            project,
            "code-review",
            script_body="import sys; sys.exit(0)\n",
        )
        runner = SkillRunner(project)
        runner.run("code-review")
        assert self._last_record(project)["agent"] == "tech-lead"

    def test_explicit_param_overrides_env(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CATAFORGE_INVOKING_AGENT", "tech-lead")
        _write_skill(
            project,
            "code-review",
            script_body="import sys; sys.exit(0)\n",
        )
        runner = SkillRunner(project)
        runner.run("code-review", agent="reflector")
        assert self._last_record(project)["agent"] == "reflector"

    def test_legacy_reviewer_fallback(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No param, no env — keep the historical 'reviewer'
        attribution so existing review-class skill flows don't change
        meaning."""
        monkeypatch.delenv("CATAFORGE_INVOKING_AGENT", raising=False)
        _write_skill(
            project,
            "code-review",
            script_body="import sys; sys.exit(0)\n",
        )
        runner = SkillRunner(project)
        runner.run("code-review")
        assert self._last_record(project)["agent"] == "reviewer"
