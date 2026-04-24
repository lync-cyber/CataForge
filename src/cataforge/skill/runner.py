"""Skill script executor — run executable skills in a controlled environment.

Built-in skills are invoked via ``python -m cataforge.skill.builtins.<pkg>.<script>``.
Project-level skills are invoked via ``python <script_path>``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.skill.loader import SkillLoader, SkillMeta

# Review skills whose runs should be recorded in docs/EVENT-LOG.jsonl so
# ``cataforge doctor`` / retrospectives can compute the "quality-gate
# to-work ratio" (how often Layer 1 actually ran vs degraded). Other
# skills stay out of the log to avoid schema drift — the log is
# intentionally narrow (see docs/architecture/quality-and-learning.md).
_EVENT_LOGGED_SKILLS: frozenset[str] = frozenset({
    "code-review",
    "sprint-review",
    "doc-review",
})


class SkillRunner:
    """Execute skill scripts with proper environment setup."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._paths = ProjectPaths(project_root or find_project_root())
        self._loader = SkillLoader(self._paths.root)

    def run(
        self,
        skill_id: str,
        args: list[str] | None = None,
        script_name: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a skill's script.

        Args:
            skill_id: Skill identifier (e.g. "code-review").
            args: Arguments to pass to the script.
            script_name: Specific script name (if skill has multiple). Defaults to first.

        Returns:
            CompletedProcess result.
        """
        meta = self._loader.get_skill(skill_id)
        if meta is None:
            raise ValueError(f"Skill not found: {skill_id}")

        if not meta.scripts:
            raise ValueError(f"Skill {skill_id} has no executable scripts")

        script_entry = self._find_script(meta, script_name)
        if script_entry is None:
            raise ValueError(
                f"Script {script_name!r} not found in skill {skill_id}. "
                f"Available: {[s['name'] for s in meta.scripts]}"
            )

        env = self._build_env()

        if meta.builtin:
            module_path = f"cataforge.skill.builtins.{script_entry['module']}"
            cmd = [sys.executable, "-m", module_path] + (args or [])
        else:
            script_path = self._paths.skill_dir(skill_id) / script_entry["entry"]
            if not script_path.is_file():
                raise FileNotFoundError(f"Script file not found: {script_path}")
            cmd = [sys.executable, str(script_path)] + (args or [])

        result = subprocess.run(
            cmd,
            cwd=str(self._paths.root),
            env=env,
            capture_output=True,
            text=True,
        )

        self._emit_run_event(skill_id, script_entry, result.returncode)
        return result

    def _emit_run_event(
        self,
        skill_id: str,
        script_entry: dict[str, str],
        returncode: int,
    ) -> None:
        """Best-effort: append a ``state_change`` record to EVENT-LOG.jsonl.

        Only runs for the three review skills (Layer 1 quality gates) — the
        event log is a narrow, schema-validated stream and we don't want to
        widen it with every skill invocation. Event emission is best-effort:
        any failure here (log unwritable, schema drift, etc.) is swallowed
        so the caller still sees the subprocess result.

        The phase is taken from ``CATAFORGE_EVENT_PHASE`` when set (so
        orchestrator-driven runs can attribute to the right lifecycle
        phase); otherwise defaults to ``development``, which is where
        Layer 1 scripts are actually executed.
        """
        if skill_id not in _EVENT_LOGGED_SKILLS:
            return
        try:
            from cataforge.core.event_log import append_event, build_record
        except Exception:
            return

        phase = os.environ.get("CATAFORGE_EVENT_PHASE") or "development"
        if returncode == 0:
            detail = f"skill-run: {skill_id} Layer 1 passed"
            status = "completed"
        elif returncode == 1:
            detail = f"skill-run: {skill_id} Layer 1 reported issues"
            status = "needs_revision"
        else:
            detail = (
                f"skill-run: {skill_id} Layer 1 exit={returncode} "
                "(unreachable or runtime error)"
            )
            status = "blocked"

        try:
            record = build_record(
                event="state_change",
                phase=phase,
                detail=detail,
                agent="reviewer",
                status=status,
                ref=f"skill:{skill_id}/{script_entry['name']}",
            )
            append_event(self._paths.root, record)
        except Exception:
            # EVENT-LOG append is observability, not control flow. A
            # malformed phase or an unwritable docs/ directory must not
            # take down a passing lint run.
            return

    def _find_script(self, meta: SkillMeta, script_name: str | None) -> dict[str, str] | None:
        if script_name is None:
            return meta.scripts[0] if meta.scripts else None
        for s in meta.scripts:
            if s["name"] == script_name:
                return s
        return None

    def _build_env(self) -> dict[str, str]:
        """Build environment for skill script execution."""
        env = os.environ.copy()
        env["CATAFORGE_PROJECT_ROOT"] = str(self._paths.root)
        return env
