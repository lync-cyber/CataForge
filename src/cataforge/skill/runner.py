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
        *,
        agent: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a skill's script.

        Args:
            skill_id: Skill identifier (e.g. "code-review").
            args: Arguments to pass to the script.
            script_name: Specific script name (if skill has multiple). Defaults to first.
            agent: Agent that initiated this run (used as ``agent`` field
                in the EVENT-LOG state_change record). When ``None``, falls
                back to ``CATAFORGE_INVOKING_AGENT`` env var, then to
                ``"reviewer"`` (preserves prior behaviour for callers that
                don't yet pass attribution).

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

        # Force UTF-8 on subprocess pipes — Windows cp1252 default would
        # raise UnicodeDecodeError when a skill prints arrows / Chinese
        # findings (e.g. framework_check.py). Pairs with ensure_utf8_stdio()
        # in the script's main(): both ends agree on UTF-8.
        result = subprocess.run(
            cmd,
            cwd=str(self._paths.root),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self._emit_run_event(meta, script_entry, result.returncode, agent=agent)
        return result

    def _emit_run_event(
        self,
        meta: SkillMeta,
        script_entry: dict[str, str],
        returncode: int,
        *,
        agent: str | None = None,
    ) -> None:
        """Best-effort: append a ``state_change`` record to EVENT-LOG.jsonl.

        Gated on ``meta.record_to_event_log`` (driven from SKILL.md
        frontmatter / builtin defaults — see SkillLoader). Keeping the
        decision in metadata means a new review-class skill only needs to
        flip one flag, instead of editing a hardcoded set in two places.

        Event emission is best-effort: any failure here (log unwritable,
        schema drift, etc.) is swallowed so the caller still sees the
        subprocess result.

        The phase is taken from ``CATAFORGE_EVENT_PHASE`` when set (so
        orchestrator-driven runs can attribute to the right lifecycle
        phase); otherwise defaults to ``development``, which is where
        Layer 1 scripts are actually executed.

        Agent attribution: if the caller didn't pass ``agent=``, we read
        ``CATAFORGE_INVOKING_AGENT`` from the env so an upstream
        orchestrator/dispatcher can `export` it once and have downstream
        ``cataforge skill run`` invocations attribute back. Final fallback
        is ``"reviewer"`` for backward compat with existing review skills.
        """
        if not meta.record_to_event_log:
            return
        skill_id = meta.id
        try:
            from cataforge.core.event_log import append_event, build_record
        except Exception:
            return

        phase = os.environ.get("CATAFORGE_EVENT_PHASE") or "development"
        attributed_agent = (
            agent
            or os.environ.get("CATAFORGE_INVOKING_AGENT")
            or "reviewer"
        )
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
                agent=attributed_agent,
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
