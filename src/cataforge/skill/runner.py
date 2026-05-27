"""Skill script executor — run executable skills in a controlled environment.

Built-in skills are invoked via ``python -m cataforge.skill.builtins.<pkg>.<script>``.
Project-level skills are invoked via ``python <script_path>``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.skill.loader import SkillLoader, SkillMeta
from cataforge.utils.run_subprocess import run as run_proc

_DEFAULT_TIMEOUT_SECS = 300


class SkillTimeoutError(RuntimeError):
    """Raised when a skill script exceeds its allowed execution time."""

    def __init__(self, skill_id: str, timeout_secs: int | float) -> None:
        self.skill_id = skill_id
        self.timeout_secs = timeout_secs
        super().__init__(
            f"Skill {skill_id!r} exceeded timeout of {timeout_secs}s"
        )


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
        timeout: int | float | None = None,
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
            timeout: Maximum seconds to allow the script to run. Defaults to
                ``SKILL_RUNNER_TIMEOUT_DEFAULT_SECS`` from framework constants
                (300 s). Pass ``0`` or a negative value to disable the limit.

        Raises:
            SkillTimeoutError: If the script exceeds *timeout* seconds.

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

        effective_timeout: float | None
        if timeout is None:
            effective_timeout = _DEFAULT_TIMEOUT_SECS
        elif timeout <= 0:
            effective_timeout = None
        else:
            effective_timeout = float(timeout)

        # The wrapper defaults to text=True + encoding=utf-8 + errors=replace,
        # which is exactly what we want here: skill scripts pair with
        # ensure_utf8_stdio() so both ends agree on UTF-8, and a stray
        # non-UTF-8 byte from a child becomes a replacement char instead of
        # crashing the reader.
        t_start = time.monotonic()
        try:
            result = run_proc(
                cmd,
                cwd=self._paths.root,
                env=env,
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - t_start
            self._emit_timeout_event(
                meta, script_entry, effective_timeout, duration, agent=agent
            )
            raise SkillTimeoutError(skill_id, effective_timeout) from None

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

    def _emit_timeout_event(
        self,
        meta: SkillMeta,
        script_entry: dict[str, str],
        timeout_secs: float,
        duration: float,
        *,
        agent: str | None = None,
    ) -> None:
        """Best-effort: append a ``state_change`` record for a timed-out skill run."""
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
        try:
            record = build_record(
                event="state_change",
                phase=phase,
                detail=(
                    f"skill_timeout: {skill_id} exceeded {timeout_secs}s "
                    f"(elapsed={duration:.1f}s)"
                ),
                agent=attributed_agent,
                status="blocked",
                ref=f"skill:{skill_id}/{script_entry['name']}",
            )
            append_event(self._paths.root, record)
        except Exception:
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
