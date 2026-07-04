"""Unattended building-loop driver — cross-platform outer shell.

Drives one frozen sprint's *building* by repeatedly relaunching a fresh
``claude -p`` (each iteration a clean context), reading the durable
``EVENT-LOG.jsonl`` + ``git HEAD`` to decide completion / circuit-break /
progress. Never merges or deploys — the caller runs it inside a sandbox on a
feature branch. State lives entirely in files + git, so the driver can die and
be restarted from scratch.

The loop body is pure orchestration with no intelligence: the quality gate is
the orchestrator's own TDD + code-review, and the completion signal is a real
``sprint_complete`` event (emitted only after reviewer approval), never the
building agent's self-assessment.

``claude_runner`` / ``sleep`` are injectable so the whole loop is unit-testable
in-process without a live ``claude`` or wall-clock waits.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cataforge.core.event_log import (
    EventLogError,
    append_event,
    build_record,
    event_log_path,
    now_iso,
)
from cataforge.utils.run_subprocess import run as run_proc

# Per-loop operational metrics — a disposable, gitignored runtime stream
# (``.cataforge/state/``) kept out of the semantic EVENT-LOG so token/timing
# data can't pollute the audit schema. Fields the driver can fill reliably;
# token / card counts need claude-usage / dev-plan parsing and are deferred.
METRICS_REL = Path(".cataforge") / "state" / "loop-metrics.jsonl"
METRICS_FIELDS: tuple[str, ...] = (
    "iter",
    "ts",
    "sprint",
    "head_before",
    "head_after",
    "progressed",
    "files_changed",
    "duration_sec",
    "stagnation",
    "same_error",
)

# Exit codes: 0 done / 3 circuit-open / 4 hit iteration (or auto-wait) cap /
# 5 pre-flight refusal. 5 (not 2) so a supervisor distinguishes a pre-flight
# refusal from Click's own usage error, which also exits 2.
EXIT_COMPLETE = 0
EXIT_CIRCUIT = 3
EXIT_MAX_ITERATIONS = 4
EXIT_PREFLIGHT = 5

_TIMEOUT_RC = 124

# Match only structured API error-type identifiers, not prose — an orchestrator
# transcript that merely discusses rate limiting must not be mistaken for a real
# limit (that would auto-wait forever while real progress is discarded).
_RATE_LIMIT_RE = re.compile(r"rate_limit_error|overloaded_error|usage_limit", re.IGNORECASE)
_ERROR_LINE_RE = re.compile(r"error|traceback|exception|assert|fail", re.IGNORECASE)
_PATHISH_RE = re.compile(r'[A-Za-z]:?[\\/][^\s"]*')
_LINENO_RE = re.compile(r"\bline \d+|:\d+")
_WS_RE = re.compile(r"\s+")


@dataclass
class ClaudeResult:
    """One ``claude -p`` invocation's outcome the loop reasons over."""

    returncode: int
    output: str
    timed_out: bool = False


ClaudeRunner = Callable[[str, float], ClaudeResult]

# Env stamped onto the claude subprocess: a headless marker the tool-level deny
# hook (guard_dangerous) gates on, plus an autonomous commit identity so morning
# review can tell unattended commits from human ones.
UNATTENDED_ENV: dict[str, str] = {
    "CATAFORGE_UNATTENDED": "1",
    "GIT_AUTHOR_NAME": "cataforge-unattended",
    "GIT_AUTHOR_EMAIL": "unattended@cataforge.local",
    "GIT_COMMITTER_NAME": "cataforge-unattended",
    "GIT_COMMITTER_EMAIL": "unattended@cataforge.local",
}


def _default_claude_runner(prompt: str, timeout: float) -> ClaudeResult:
    argv = [
        "claude",
        "-p",
        prompt,
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    try:
        cp = run_proc(
            argv, timeout=timeout, capture_output=True, env={**os.environ, **UNATTENDED_ENV}
        )
    except subprocess.TimeoutExpired:
        return ClaudeResult(returncode=_TIMEOUT_RC, output="", timed_out=True)
    return ClaudeResult(returncode=cp.returncode, output=(cp.stdout or "") + (cp.stderr or ""))


def _git(project_root: Path, *args: str) -> str:
    cp = run_proc(["git", *args], cwd=project_root)
    return cp.stdout.strip() if cp.returncode == 0 else ""


def _event_lines(project_root: Path) -> list[str]:
    path = event_log_path(project_root)
    if not path.is_file():
        return []
    # EVENT-LOG is a UTF-8 cross-process JSONL contract (append side pins it too);
    # a host that never ran ensure_utf8 must still read the log we write.
    text = path.read_text(encoding="utf-8")  # allow-explicit-encoding: contract
    return [ln for ln in text.splitlines() if ln.strip()]


def _new_events(lines: list[str], baseline: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ln in lines[baseline:]:
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _files_changed(project_root: Path, head_before: str, head_after: str) -> int:
    if not head_before or not head_after or head_before == head_after:
        return 0
    out = _git(project_root, "diff", "--name-only", head_before, head_after)
    return len([ln for ln in out.splitlines() if ln.strip()])


def metrics_path(project_root: Path) -> Path:
    return project_root / METRICS_REL


def build_metrics_record(
    *,
    iteration: int,
    sprint: str,
    head_before: str,
    head_after: str,
    progressed: bool,
    files_changed: int,
    duration_sec: float,
    stagnation: int,
    same_error: int,
) -> dict[str, Any]:
    return {
        "iter": iteration,
        "ts": now_iso(),
        "sprint": sprint,
        "head_before": head_before,
        "head_after": head_after,
        "progressed": progressed,
        "files_changed": files_changed,
        "duration_sec": round(duration_sec, 3),
        "stagnation": stagnation,
        "same_error": same_error,
    }


def _append_metrics(project_root: Path, record: dict[str, Any]) -> None:
    # Best-effort observability: a metrics write failure must not affect the loop.
    # Catch ValueError too — a non-UTF-8 host would raise UnicodeEncodeError
    # (a ValueError, not an OSError) when writing a non-ASCII sprint id.
    with contextlib.suppress(OSError, ValueError):
        path = metrics_path(project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open(
            "a", encoding="utf-8", newline="\n"
        ) as f:  # allow-explicit-encoding: contract
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n")


def rate_limited(output: str) -> bool:
    """A rate / usage-limit signal — a *wait*, not stagnation (must not burn budget)."""
    return bool(_RATE_LIMIT_RE.search(output))


def error_signature(output: str) -> str:
    """Fingerprint of the *last* error line (the final exception in a traceback —
    most specific), with volatile file paths and line/column numbers stripped but
    operands kept, so the same root cause folds while distinct failures don't."""
    matches = [ln for ln in output.splitlines() if _ERROR_LINE_RE.search(ln)]
    if not matches:
        return ""
    sig = _LINENO_RE.sub("", _PATHISH_RE.sub("", matches[-1]))
    return _WS_RE.sub(" ", sig).strip()


def build_prompt(sprint: str, card_revision_ceiling: int) -> str:
    return (
        f"继续推进 {sprint}（无人值守 building 模式，按 "
        ".cataforge/references/unattended-overrides.md 执行）：\n"
        f"1. 按 Startup Protocol 读 §项目状态 + dev-plan 定位到 {sprint} 下一张 pending 任务卡。\n"
        "2. 经 tdd-engine 跑 TDD，GREEN 后调 code-review；approved 才算该卡完成，"
        "置 status=done 并 git commit 到当前 feature 分支。\n"
        f"3. 任一任务卡累计 needs_revision 达 {card_revision_ceiling} 次："
        "标该卡 blocked，emit circuit_open，跳下一张可并行卡。\n"
        f"4. {sprint} 全部任务卡 approved：emit sprint_complete（ref=dev-plan#{sprint}）。\n"
        "约束：禁止 AskUserQuestion / 任何 needs_input（遇到即视同 blocked + circuit_open）；"
        "禁止 PR merge、禁止 deploy、禁止改 PRD/ARCH/DEV-PLAN。"
    )


def _emit_circuit_open(project_root: Path, sprint: str, detail: str) -> None:
    # Best-effort telemetry: the exit code is the authoritative breaker signal,
    # so a failed event write must not change the outcome.
    with contextlib.suppress(EventLogError, OSError):
        append_event(
            project_root,
            build_record(
                event="circuit_open",
                phase="development",
                agent="orchestrator",
                ref=f"dev-plan#{sprint}",
                detail=detail,
            ),
        )


def run_building_loop(
    project_root: Path,
    sprint: str,
    *,
    max_iterations: int,
    stagnation_threshold: int,
    card_revision_ceiling: int,
    same_error_ceiling: int,
    iter_timeout_sec: float,
    ratelimit_wait_sec: float,
    claude_runner: ClaudeRunner | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Run the loop for *sprint*; return an exit code (see module constants)."""
    runner = claude_runner or _default_claude_runner

    # Pre-flight: never on main (full frozen-upstream checks live in cataforge doctor).
    if _git(project_root, "rev-parse", "--abbrev-ref", "HEAD") == "main":
        return EXIT_PREFLIGHT

    # Baseline: only events this run appends count, so a historical
    # sprint_complete / circuit_open can't spuriously trip completion.
    baseline = len(_event_lines(project_root))
    prompt = build_prompt(sprint, card_revision_ceiling)

    iterations = 0
    stagnation = 0
    same_error = 0
    consecutive_waits = 0
    last_sig = ""
    complete_ref = f"dev-plan#{sprint}"

    while iterations < max_iterations:
        head_before = _git(project_root, "rev-parse", "HEAD")
        events_before = len(_event_lines(project_root))

        started = time.monotonic()
        result = runner(prompt, iter_timeout_sec)

        # Rate-limit / timeout is a wait, not no-progress: retry without
        # consuming iteration / stagnation / same-error budget. Only a genuine
        # non-zero exit counts as a limit — a successful run whose transcript
        # merely mentions one is real progress, not a wait.
        if result.timed_out or (result.returncode != 0 and rate_limited(result.output)):
            consecutive_waits += 1
            # Backstop: a limit that never clears (or a mis-detected wait) must
            # not spin forever — hand back after max_iterations consecutive waits.
            if consecutive_waits >= max_iterations:
                return EXIT_MAX_ITERATIONS
            if ratelimit_wait_sec > 0:
                sleep(ratelimit_wait_sec)
            continue

        iterations += 1
        consecutive_waits = 0
        duration = time.monotonic() - started
        new = _new_events(_event_lines(project_root), baseline)
        if any(r.get("event") == "sprint_complete" and r.get("ref") == complete_ref for r in new):
            return EXIT_COMPLETE
        # Only a sprint-level circuit_open (orchestrator gave up on the whole
        # sprint, ref=dev-plan#sprint) is terminal. Card-level breaks
        # (ref=<task-card>) mean "blocked this card, skip to the next" and must
        # NOT halt the loop — see references/unattended-overrides.md item 3.
        if any(r.get("event") == "circuit_open" and r.get("ref") == complete_ref for r in new):
            return EXIT_CIRCUIT

        head_after = _git(project_root, "rev-parse", "HEAD")
        events_after = len(_event_lines(project_root))
        progressed = head_after != head_before or events_after > events_before
        stagnation = 0 if progressed else stagnation + 1

        sig = error_signature(result.output)
        if sig and sig == last_sig:
            same_error += 1
        else:
            same_error = 0
            last_sig = sig

        _append_metrics(
            project_root,
            build_metrics_record(
                iteration=iterations,
                sprint=sprint,
                head_before=head_before,
                head_after=head_after,
                progressed=progressed,
                files_changed=_files_changed(project_root, head_before, head_after),
                duration_sec=duration,
                stagnation=stagnation,
                same_error=same_error,
            ),
        )

        if stagnation >= stagnation_threshold:
            _emit_circuit_open(project_root, sprint, f"stagnation: 连续 {stagnation} 轮无进展")
            return EXIT_CIRCUIT
        if same_error >= same_error_ceiling:
            _emit_circuit_open(
                project_root, sprint, f"same-error: 连续 {same_error} 轮同一错误签名"
            )
            return EXIT_CIRCUIT

    return EXIT_MAX_ITERATIONS
