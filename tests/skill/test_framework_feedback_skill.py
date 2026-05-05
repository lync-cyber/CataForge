"""Smoke tests for the ``framework-feedback`` builtin skill.

Three-layer coverage:

1. Loader discovers it as a builtin with executable scripts.
2. Direct ``main()`` entry point (no subprocess) renders markdown.
3. ``cataforge skill run framework-feedback -- ...`` end-to-end via the
   real SkillRunner (subprocess fork) — proves the doctor reachability
   check will pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.core.corrections import record_correction
from cataforge.skill.builtins.framework_feedback import CHECKS_MANIFEST
from cataforge.skill.builtins.framework_feedback.framework_feedback import main
from cataforge.skill.loader import SkillLoader
from cataforge.skill.runner import SkillRunner


def _bootstrap(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps(
            {"version": "0.2.1-test", "runtime": {"platform": "claude-code"}}
        ),
        encoding="utf-8",
    )
    return tmp_path


# ─── 1. discovery ─────────────────────────────────────────────────────────────


class TestDiscovery:
    def test_loader_finds_framework_feedback_builtin(
        self, tmp_path: Path
    ) -> None:
        project = _bootstrap(tmp_path)
        loader = SkillLoader(project_root=project)
        meta = loader.get_skill("framework-feedback")
        assert meta is not None
        assert meta.builtin is True
        assert meta.scripts, "skill must have at least one entry point"
        # Doctor's reachability check uses meta.scripts non-empty as the gate.

    def test_record_to_event_log_flag_inherited(self, tmp_path: Path) -> None:
        """The runner's `_emit_run_event` only fires when this is True."""
        project = _bootstrap(tmp_path)
        loader = SkillLoader(project_root=project)
        meta = loader.get_skill("framework-feedback")
        assert meta is not None
        assert meta.record_to_event_log is True

    def test_checks_manifest_is_non_empty(self) -> None:
        # framework-review B3 will fail if the manifest goes empty.
        assert CHECKS_MANIFEST
        assert all("id" in c for c in CHECKS_MANIFEST)


# ─── 2. direct main() ─────────────────────────────────────────────────────────


class TestMainEntry:
    def test_bug_kind_writes_markdown(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        project = _bootstrap(tmp_path)
        rc = main(
            [
                "bug",
                "--summary", "smoke from skill",
                "--root", str(project),
                "--skip-framework-review",
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "## Environment" in out
        assert "smoke from skill" in out

    def test_correction_export_refuses_without_signals(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        project = _bootstrap(tmp_path)
        rc = main(
            [
                "correction-export",
                "--summary", "x",
                "--root", str(project),
            ]
        )
        assert rc == 1
        err = capsys.readouterr().err
        assert "upstream-gap" in err

    def test_correction_export_emits_when_signals_present(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        project = _bootstrap(tmp_path)
        for i in range(3):
            record_correction(
                project,
                trigger="review-flag",
                agent="reviewer",
                phase="review",
                question=f"gap-{i}",
                baseline="b",
                actual="a",
                deviation="upstream-gap",
            )
        rc = main(
            [
                "correction-export",
                "--summary", "see attached",
                "--root", str(project),
                "--threshold", "3",
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        for i in range(3):
            assert f"gap-{i}" in out

    def test_out_flag_writes_file(self, tmp_path: Path) -> None:
        project = _bootstrap(tmp_path)
        target = project / "docs" / "feedback" / "out.md"
        rc = main(
            [
                "bug",
                "--summary", "x",
                "--root", str(project),
                "--skip-framework-review",
                "--out", str(target),
            ]
        )
        assert rc == 0
        assert target.is_file()
        assert "## Environment" in target.read_text(encoding="utf-8")


# ─── 3. end-to-end via SkillRunner (real subprocess) ──────────────────────────


class TestRunnerSmoke:
    def test_skill_runner_invokes_builtin(self, tmp_path: Path) -> None:
        """Drives a real ``python -m cataforge.skill.builtins.framework_feedback...``
        fork. Slow (~1s) but it's the only thing that proves the entire
        wiring chain works the way ``cataforge skill run`` will use it."""
        project = _bootstrap(tmp_path)
        runner = SkillRunner(project_root=project)
        result = runner.run(
            "framework-feedback",
            ["bug", "--summary", "subprocess smoke", "--skip-framework-review"],
            agent="orchestrator",
        )
        assert result.returncode == 0, (
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        assert "## Environment" in result.stdout
        assert "subprocess smoke" in result.stdout

    def test_runner_emits_state_change_event(self, tmp_path: Path) -> None:
        """Because ``framework-feedback`` is in ``_BUILTIN_EVENT_LOGGED``, the
        runner appends a ``state_change`` record. This gives the project a
        durable timeline of when feedback was drafted."""
        project = _bootstrap(tmp_path)
        runner = SkillRunner(project_root=project)
        result = runner.run(
            "framework-feedback",
            ["bug", "--summary", "x", "--skip-framework-review"],
            agent="orchestrator",
        )
        assert result.returncode == 0
        log = project / "docs" / "EVENT-LOG.jsonl"
        assert log.is_file(), "EVENT-LOG should have been created by the runner"
        lines = [
            json.loads(line)
            for line in log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        skill_run_events = [
            r for r in lines
            if r.get("event") == "state_change"
            and r.get("ref", "").startswith("skill:framework-feedback/")
        ]
        assert skill_run_events, f"no state_change for framework-feedback in {lines}"
        assert skill_run_events[-1]["agent"] == "orchestrator"
