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
)
from cataforge.utils.run_subprocess import run as run_proc

# Exit codes: 0 done / 2 pre-flight refusal / 3 circuit-open / 4 hit iteration cap.
EXIT_COMPLETE = 0
EXIT_PREFLIGHT = 2
EXIT_CIRCUIT = 3
EXIT_MAX_ITERATIONS = 4

_TIMEOUT_RC = 124

_RATE_LIMIT_RE = re.compile(
    r'"(?:type|error)"[^}]*(?:rate_limit|usage[_-]?limit)|rate.limit|usage limit|overloaded',
    re.IGNORECASE,
)
_ERROR_LINE_RE = re.compile(r"error|traceback|exception|assert|fail", re.IGNORECASE)
_DIGITS_RE = re.compile(r"\d+")
_PATHISH_RE = re.compile(r'[A-Za-z]:?[\\/][^\s"]*')
_WS_RE = re.compile(r"\s+")


@dataclass
class ClaudeResult:
    """One ``claude -p`` invocation's outcome the loop reasons over."""

    returncode: int
    output: str
    timed_out: bool = False


ClaudeRunner = Callable[[str, float], ClaudeResult]


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
        cp = run_proc(argv, timeout=timeout, capture_output=True)
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
    return [ln for ln in path.read_text().splitlines() if ln.strip()]


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


def rate_limited(output: str) -> bool:
    """A rate / usage-limit signal — a *wait*, not stagnation (must not burn budget)."""
    return bool(_RATE_LIMIT_RE.search(output))


def error_signature(output: str) -> str:
    """Stable fingerprint of the first error frame, with volatile paths / line
    numbers stripped, so a repeated failure is recognisable even as HEAD moves."""
    for line in output.splitlines():
        if _ERROR_LINE_RE.search(line):
            sig = _PATHISH_RE.sub("", _DIGITS_RE.sub("", line))
            return _WS_RE.sub(" ", sig).strip()
    return ""


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
    last_sig = ""
    complete_ref = f"dev-plan#{sprint}"

    while iterations < max_iterations:
        head_before = _git(project_root, "rev-parse", "HEAD")
        events_before = len(_event_lines(project_root))

        result = runner(prompt, iter_timeout_sec)

        # Rate-limit / timeout is a wait, not no-progress: retry without
        # consuming iteration / stagnation / same-error budget.
        if result.timed_out or rate_limited(result.output):
            if ratelimit_wait_sec > 0:
                sleep(ratelimit_wait_sec)
            continue

        iterations += 1
        new = _new_events(_event_lines(project_root), baseline)
        if any(r.get("event") == "sprint_complete" and r.get("ref") == complete_ref for r in new):
            return EXIT_COMPLETE
        if any(r.get("event") == "circuit_open" for r in new):
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

        if stagnation >= stagnation_threshold:
            _emit_circuit_open(project_root, sprint, f"stagnation: 连续 {stagnation} 轮无进展")
            return EXIT_CIRCUIT
        if same_error >= same_error_ceiling:
            _emit_circuit_open(
                project_root, sprint, f"same-error: 连续 {same_error} 轮同一错误签名"
            )
            return EXIT_CIRCUIT

    return EXIT_MAX_ITERATIONS
