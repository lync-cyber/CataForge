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

Liveness is supervised on the stream, not on a deadline: the runner reads the
``stream-json`` output incrementally, every event line is a heartbeat, and only
"silent for longer than the silence timeout" counts as a suspected hang. The
total per-session timeout is a loose backstop against pathological runaway
sessions, not the primary kill criterion — a healthy long task (a full test
gate can be legitimately silent for 10+ minutes) must never be killed for
merely taking time.

``claude_runner`` / ``sleep`` are injectable so the whole loop is unit-testable
in-process without a live ``claude`` or wall-clock waits.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from cataforge.core.event_log import (
    EventLogError,
    append_event,
    build_record,
    event_log_path,
    now_iso,
)
from cataforge.utils.run_subprocess import run as run_proc

# Per-loop operational streams — disposable, gitignored runtime data
# (``.cataforge/state/``) kept out of the semantic EVENT-LOG so token/timing
# data can't pollute the audit schema. ``loop-metrics.jsonl`` holds one record
# per launch (iteration or wait); ``loop-transcripts/iter-NNN.jsonl`` holds the
# raw stream-json of each launch, keyed by the same attempt number that is
# stamped into ``CATAFORGE_UNATTENDED_ITER`` — the correlation key across
# metrics / EVENT-LOG / transcript.
METRICS_REL = Path(".cataforge") / "state" / "loop-metrics.jsonl"
TRANSCRIPTS_REL = Path(".cataforge") / "state" / "loop-transcripts"
METRICS_FIELDS: tuple[str, ...] = (
    "kind",
    "iter",
    "attempt",
    "ts",
    "sprint",
    "head_before",
    "head_after",
    "progressed",
    "files_changed",
    "duration_sec",
    "stagnation",
    "returncode",
    "session_id",
    "tokens_in",
    "tokens_out",
    "cache_read_tokens",
    "cost_usd",
    "output_tail",
)
METRICS_WAIT_FIELDS: tuple[str, ...] = (
    "kind",
    "attempt",
    "ts",
    "sprint",
    "reason",
    "timeout_reason",
    "duration_sec",
    "consecutive_waits",
    "head_moved",
    "session_id",
)

_OUTPUT_TAIL_BYTES = 4096

# Exit codes: 0 done / 3 circuit-open / 4 hit iteration (or auto-wait) cap /
# 5 pre-flight refusal. 5 (not 2) so a supervisor distinguishes a pre-flight
# refusal from Click's own usage error, which also exits 2.
EXIT_COMPLETE = 0
EXIT_CIRCUIT = 3
EXIT_MAX_ITERATIONS = 4
EXIT_PREFLIGHT = 5

_TIMEOUT_RC = 124

# Structured API error-types plus the subscription-cap phrasings the CLI prints
# to stderr ("usage limit reached", "5-hour limit reached"). Prose can't false-
# trigger a wait: rate_limited is consulted only on a non-zero exit, so a healthy
# run that merely mentions a limit is real progress, not a wait.
_RATE_LIMIT_RE = re.compile(
    r"rate[ _]limit(?:_error)?"
    r"|overloaded_error"
    r"|usage[ _]limit"
    r"|(?:\d+-hour|\d+-day|hourly|daily|weekly|monthly)\s+limit reached",
    re.IGNORECASE,
)

# Only genuine forward-movement events reset the stagnation counter. Bookkeeping
# / churn events (agent_dispatch, agent_return, tdd_phase, session_*,
# review_verdict, revision_start) are appended every round even when nothing
# lands, so counting *any* new event as progress would mask a stuck sprint.
_PROGRESS_EVENTS = frozenset(
    {"state_change", "circuit_open", "sprint_complete", "doc_finalize", "phase_start", "phase_end"}
)


@dataclass(frozen=True)
class BuildTarget:
    """What the loop drives to completion.

    ``standard`` / ``agile-lite`` build one frozen sprint (``dev-plan#sprint-N``);
    ``agile-prototype`` has no sprint grouping and builds the brief's task cards
    (``brief#tasks``). ``ref`` is the completion / circuit-open key the loop
    matches on; ``label`` is the human / metrics name.
    """

    ref: str
    label: str
    prototype: bool = False


def sprint_target(sprint: str) -> BuildTarget:
    """dev-plan sprint target (standard / agile-lite)."""
    return BuildTarget(ref=f"dev-plan#{sprint}", label=sprint)


def prototype_target() -> BuildTarget:
    """agile-prototype brief target — no sprint, keyed on ``brief#tasks``."""
    return BuildTarget(ref="brief#tasks", label="brief", prototype=True)


@dataclass(frozen=True)
class IterLimits:
    """Per-launch supervision contract handed to the runner.

    ``silence_timeout_sec`` is the liveness criterion (kill only after this
    long with zero stream output); ``total_timeout_sec`` is the loose backstop
    against pathological runaway sessions. ``transcript_path`` receives the raw
    stream incrementally; ``attempt`` numbers every launch (waits included) and
    is exported as ``CATAFORGE_UNATTENDED_ITER`` for cross-stream correlation.
    """

    silence_timeout_sec: float
    total_timeout_sec: float
    transcript_path: Path | None = None
    attempt: int = 1


@dataclass
class ClaudeResult:
    """One ``claude -p`` invocation's outcome the loop reasons over.

    ``timeout_reason`` distinguishes a silence kill (suspected hang) from the
    total-duration backstop when ``timed_out`` is set.
    """

    returncode: int
    output: str
    timed_out: bool = False
    timeout_reason: str | None = None


ClaudeRunner = Callable[[str, IterLimits], ClaudeResult]

# Env stamped onto the claude subprocess: a headless marker the tool-level deny
# hook (guard_dangerous) gates on, plus an autonomous commit identity so morning
# review can tell unattended commits from human ones. The per-launch
# ``CATAFORGE_UNATTENDED_ITER`` correlation key is added by the runner from
# ``IterLimits.attempt``.
UNATTENDED_ENV: dict[str, str] = {
    "CATAFORGE_UNATTENDED": "1",
    "GIT_AUTHOR_NAME": "cataforge-unattended",
    "GIT_AUTHOR_EMAIL": "unattended@cataforge.local",
    "GIT_COMMITTER_NAME": "cataforge-unattended",
    "GIT_COMMITTER_EMAIL": "unattended@cataforge.local",
}


def _kill_tree(proc: subprocess.Popen[str]) -> None:
    # Kill the whole session process tree: the claude CLI spawns tool
    # subprocesses (test runners, git) that must not outlive a kill.
    if sys.platform == "win32":
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            run_proc(["taskkill", "/F", "/T", "/PID", str(proc.pid)], timeout=30)
    else:
        with contextlib.suppress(OSError):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    with contextlib.suppress(OSError):
        proc.kill()


def _pump_stream(
    stream: IO[str],
    lines: list[str],
    last_output: list[float],
    transcript_path: Path | None,
) -> None:
    transcript: IO[str] | None = None
    if transcript_path is not None:
        with contextlib.suppress(OSError):
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript = transcript_path.open(
                "a", encoding="utf-8", newline="\n"
            )  # allow-explicit-encoding: contract
    try:
        for line in stream:
            last_output[0] = time.monotonic()
            lines.append(line)
            if transcript is not None:
                with contextlib.suppress(OSError, ValueError):
                    transcript.write(line)
                    transcript.flush()
    except (OSError, ValueError):
        pass
    finally:
        if transcript is not None:
            with contextlib.suppress(OSError):
                transcript.close()


def run_streaming(argv: list[str], limits: IterLimits, env: dict[str, str] | None) -> ClaudeResult:
    """Run *argv* under stream-silence liveness supervision.

    Reads stdout (stderr merged) incrementally: every line is a heartbeat and
    is appended to ``limits.transcript_path`` as it arrives, so a killed or
    crashed session still leaves its partial transcript on disk. Kills the
    process tree only on stream silence > ``silence_timeout_sec`` or total
    runtime > ``total_timeout_sec``.
    """
    popen_kwargs: dict[str, Any] = {}
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True  # enables killpg on the whole tree
    try:
        # The run-to-completion wrapper can't observe a live child; liveness
        # supervision needs an incrementally-read Popen stream.
        proc = subprocess.Popen(  # noqa: S603  # allow-raw-subprocess: streaming read
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",  # allow-explicit-encoding: contract
            errors="replace",
            env=env,
            **popen_kwargs,
        )
    except FileNotFoundError:
        return ClaudeResult(returncode=127, output=f"{argv[0]} executable not found")

    started = time.monotonic()
    lines: list[str] = []
    last_output = [started]
    assert proc.stdout is not None
    pump = threading.Thread(
        target=_pump_stream,
        args=(proc.stdout, lines, last_output, limits.transcript_path),
        daemon=True,
    )
    pump.start()

    timeout_reason: str | None = None
    while True:
        try:
            proc.wait(timeout=1.0)
            break
        except subprocess.TimeoutExpired:
            now = time.monotonic()
            if now - last_output[0] > limits.silence_timeout_sec:
                timeout_reason = "silence"
            elif now - started > limits.total_timeout_sec:
                timeout_reason = "total"
            if timeout_reason is not None:
                _kill_tree(proc)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=30)
                break
    pump.join(timeout=10)

    output = "".join(lines)
    if timeout_reason is not None:
        return ClaudeResult(
            returncode=_TIMEOUT_RC, output=output, timed_out=True, timeout_reason=timeout_reason
        )
    return ClaudeResult(returncode=proc.returncode or 0, output=output)


def _default_claude_runner(prompt: str, limits: IterLimits) -> ClaudeResult:
    argv = [
        "claude",
        "-p",
        prompt,
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    env = {
        **os.environ,
        **UNATTENDED_ENV,
        "CATAFORGE_UNATTENDED_ITER": str(limits.attempt),
    }
    return run_streaming(argv, limits, env)


def _git(project_root: Path, *args: str) -> str:
    # Missing git ⇒ "" ⇒ pre-flight refuses (fail-closed), never a raw traceback.
    try:
        cp = run_proc(["git", *args], cwd=project_root)
    except FileNotFoundError:
        return ""
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


def transcript_path(project_root: Path, attempt: int) -> Path:
    return project_root / TRANSCRIPTS_REL / f"iter-{attempt:03d}.jsonl"


def extract_session_id(output: str) -> str | None:
    """First ``session_id`` in a stream-json transcript (init event), or None."""
    for ln in output.splitlines():
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("session_id"), str):
            return str(rec["session_id"])
    return None


def extract_result_stats(output: str) -> dict[str, Any]:
    """Usage / cost from the stream-json terminal ``result`` event.

    All-None on any parse failure — cost accounting is observability, never a
    reason to fail a round.
    """
    stats: dict[str, Any] = {
        "tokens_in": None,
        "tokens_out": None,
        "cache_read_tokens": None,
        "cost_usd": None,
    }
    for ln in reversed(output.splitlines()):
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if not (isinstance(rec, dict) and rec.get("type") == "result"):
            continue
        usage = rec.get("usage")
        if isinstance(usage, dict):
            for key, src in (
                ("tokens_in", "input_tokens"),
                ("tokens_out", "output_tokens"),
                ("cache_read_tokens", "cache_read_input_tokens"),
            ):
                val = usage.get(src)
                if isinstance(val, int):
                    stats[key] = val
        cost = rec.get("total_cost_usd")
        if isinstance(cost, int | float):
            stats["cost_usd"] = float(cost)
        break
    return stats


def _output_tail(output: str) -> str:
    return output[-_OUTPUT_TAIL_BYTES:]


def _ensure_transcript(path: Path, output: str) -> None:
    # Injected runners don't stream to disk; persist their output post-round so
    # the transcript contract holds for every launch. The default runner already
    # wrote the file incrementally — leave it untouched.
    if not output or path.exists():
        return
    with contextlib.suppress(OSError, ValueError):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")  # allow-explicit-encoding: contract


def build_metrics_record(
    *,
    iteration: int,
    attempt: int,
    sprint: str,
    head_before: str,
    head_after: str,
    progressed: bool,
    files_changed: int,
    duration_sec: float,
    stagnation: int,
    returncode: int,
    session_id: str | None,
    stats: dict[str, Any],
    output_tail: str | None,
) -> dict[str, Any]:
    return {
        "kind": "iteration",
        "iter": iteration,
        "attempt": attempt,
        "ts": now_iso(),
        "sprint": sprint,
        "head_before": head_before,
        "head_after": head_after,
        "progressed": progressed,
        "files_changed": files_changed,
        "duration_sec": round(duration_sec, 3),
        "stagnation": stagnation,
        "returncode": returncode,
        "session_id": session_id,
        "tokens_in": stats.get("tokens_in"),
        "tokens_out": stats.get("tokens_out"),
        "cache_read_tokens": stats.get("cache_read_tokens"),
        "cost_usd": stats.get("cost_usd"),
        "output_tail": output_tail,
    }


def build_wait_record(
    *,
    attempt: int,
    sprint: str,
    reason: str,
    timeout_reason: str | None,
    duration_sec: float,
    consecutive_waits: int,
    head_moved: bool,
    session_id: str | None,
) -> dict[str, Any]:
    return {
        "kind": "wait",
        "attempt": attempt,
        "ts": now_iso(),
        "sprint": sprint,
        "reason": reason,
        "timeout_reason": timeout_reason,
        "duration_sec": round(duration_sec, 3),
        "consecutive_waits": consecutive_waits,
        "head_moved": head_moved,
        "session_id": session_id,
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


def build_prompt(
    target: BuildTarget, card_revision_ceiling: int, session_budget_min: int | None = None
) -> str:
    # Unit-of-work + budget lines bound each session cooperatively: one card
    # then a clean exit keeps the session inside any supervision window, and a
    # clean exit costs no cooldown / cold-start — the kill path stays exceptional.
    unit = (
        "5. 本会话最多完成一张任务卡即干净退出（大卡至多推进一个 TDD 相并 Mid-Progress 落盘），"
        "完成即 git commit 后结束会话，不连做下一张；外壳会拉起新会话继续。"
    )
    budget = (
        f"6. 会话时长预算约 {session_budget_min} 分钟：接近预算时收敛到可提交状态"
        "（落盘 + git commit）后干净退出。"
        if session_budget_min
        else ""
    )
    tail = unit + ("\n" + budget if budget else "")
    if target.prototype:
        return (
            "继续推进 brief.md §开发任务（无人值守 building 模式，按 "
            ".cataforge/references/unattended-overrides.md 执行）：\n"
            "1. 按 Startup Protocol 读 §项目状态 + brief.md §5 开发任务 "
            "定位下一张 pending 任务卡。\n"
            "2. 按 agile-prototype 执行模式跑 TDD（主线程内联），完成后调 code-review；"
            "approved 才算该卡完成，置 status=done 并 git commit 到当前 feature 分支。\n"
            f"3. 任一任务卡累计 needs_revision 达 {card_revision_ceiling} 次："
            "标该卡 blocked，emit circuit_open（ref 为该任务卡 id，非 brief#tasks，"
            "否则外壳会误判整体熔断提前退出），跳下一张可并行卡。\n"
            "4. brief.md 全部任务卡 approved：emit sprint_complete（ref=brief#tasks）。\n"
            f"{tail}\n"
            "约束：禁止 AskUserQuestion / 任何 needs_input（遇到即视同 blocked + circuit_open）；"
            "禁止 PR merge、禁止 deploy、禁止改 PRD/ARCH/DEV-PLAN/brief。"
        )
    sprint = target.label
    return (
        f"继续推进 {sprint}（无人值守 building 模式，按 "
        ".cataforge/references/unattended-overrides.md 执行）：\n"
        f"1. 按 Startup Protocol 读 §项目状态 + dev-plan 定位到 {sprint} 下一张 pending 任务卡。\n"
        "2. 经 tdd-engine 跑 TDD，GREEN 后调 code-review；approved 才算该卡完成，"
        "置 status=done 并 git commit 到当前 feature 分支。\n"
        f"3. 任一任务卡累计 needs_revision 达 {card_revision_ceiling} 次："
        "标该卡 blocked，emit circuit_open，跳下一张可并行卡。\n"
        f"4. {sprint} 全部任务卡 approved：emit sprint_complete（ref=dev-plan#{sprint}）。\n"
        f"{tail}\n"
        "约束：禁止 AskUserQuestion / 任何 needs_input（遇到即视同 blocked + circuit_open）；"
        "禁止 PR merge、禁止 deploy、禁止改 PRD/ARCH/DEV-PLAN。"
    )


def _emit_circuit_open(project_root: Path, target: BuildTarget, detail: str) -> None:
    # Best-effort telemetry: the exit code is the authoritative breaker signal,
    # so a failed event write must not change the outcome.
    with contextlib.suppress(EventLogError, OSError):
        append_event(
            project_root,
            build_record(
                event="circuit_open",
                phase="development",
                agent="orchestrator",
                ref=target.ref,
                detail=detail,
            ),
        )


def run_building_loop(
    project_root: Path,
    target: BuildTarget,
    *,
    max_iterations: int,
    stagnation_threshold: int,
    card_revision_ceiling: int,
    iter_timeout_sec: float,
    ratelimit_wait_sec: float,
    silence_timeout_sec: float = 900.0,
    claude_runner: ClaudeRunner | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Run the loop for *target*; return an exit code (see module constants)."""
    runner = claude_runner or _default_claude_runner

    # Pre-flight (fail-closed): only run on a confirmed feature branch. symbolic-
    # ref --short resolves the branch even on an unborn HEAD (rev-parse
    # --abbrev-ref fails there and would fall through to *proceed*); "" means
    # detached HEAD / not a repo / git missing — all cases we must refuse, never
    # assume safe. Full frozen-upstream checks live in cataforge doctor.
    branch = _git(project_root, "symbolic-ref", "--short", "HEAD")
    if branch in ("", "main"):
        return EXIT_PREFLIGHT

    # Baseline: only events this run appends count, so a historical
    # sprint_complete / circuit_open can't spuriously trip completion.
    baseline = len(_event_lines(project_root))
    prompt = build_prompt(target, card_revision_ceiling, int(iter_timeout_sec // 60) or None)

    iterations = 0
    attempt = 0
    stagnation = 0
    consecutive_waits = 0
    complete_ref = target.ref

    while iterations < max_iterations:
        attempt += 1
        head_before = _git(project_root, "rev-parse", "HEAD")
        events_before = len(_event_lines(project_root))
        tpath = transcript_path(project_root, attempt)
        limits = IterLimits(
            silence_timeout_sec=silence_timeout_sec,
            total_timeout_sec=iter_timeout_sec,
            transcript_path=tpath,
            attempt=attempt,
        )

        started = time.monotonic()
        result = runner(prompt, limits)
        duration = time.monotonic() - started
        _ensure_transcript(tpath, result.output)
        session_id = extract_session_id(result.output)

        # Rate-limit / timeout is a wait, not no-progress: retry without
        # consuming iteration / stagnation budget. Only a genuine non-zero exit
        # counts as a limit — a successful run whose transcript merely mentions
        # one is real progress, not a wait.
        if result.timed_out or (result.returncode != 0 and rate_limited(result.output)):
            reason = "timeout" if result.timed_out else "rate_limit"
            # A killed session that still committed made real progress — reset
            # the wait counter, else a long-tail card trips the cap while the
            # sprint is genuinely advancing.
            head_after = _git(project_root, "rev-parse", "HEAD")
            head_moved = bool(head_before) and bool(head_after) and head_after != head_before
            consecutive_waits = 0 if head_moved else consecutive_waits + 1
            _append_metrics(
                project_root,
                build_wait_record(
                    attempt=attempt,
                    sprint=target.label,
                    reason=reason,
                    timeout_reason=result.timeout_reason,
                    duration_sec=duration,
                    consecutive_waits=consecutive_waits,
                    head_moved=head_moved,
                    session_id=session_id,
                ),
            )
            # Backstop: a limit that never clears (or a mis-detected wait) must
            # not spin forever — hand back after max_iterations consecutive waits.
            if consecutive_waits >= max_iterations:
                return EXIT_MAX_ITERATIONS
            # Only a rate limit needs a cooldown; a timeout kill can relaunch
            # immediately — sleeping after it is pure lost wall-clock.
            if reason == "rate_limit" and ratelimit_wait_sec > 0:
                sleep(ratelimit_wait_sec)
            continue

        iterations += 1
        consecutive_waits = 0
        lines_after = _event_lines(project_root)
        new = _new_events(lines_after, baseline)

        head_after = _git(project_root, "rev-parse", "HEAD")
        # Progress = a commit (HEAD moved) or a real forward-movement event this
        # round — never mere bookkeeping / churn events (see _PROGRESS_EVENTS),
        # which would otherwise reset stagnation forever on a stuck card.
        round_events = _new_events(lines_after, events_before)
        progressed = head_after != head_before or any(
            r.get("event") in _PROGRESS_EVENTS for r in round_events
        )
        stagnation = 0 if progressed else stagnation + 1

        # Metrics before any terminal return so completion / circuit rounds are
        # accounted too — a run must never finish with an empty metrics stream.
        _append_metrics(
            project_root,
            build_metrics_record(
                iteration=iterations,
                attempt=attempt,
                sprint=target.label,
                head_before=head_before,
                head_after=head_after,
                progressed=progressed,
                files_changed=_files_changed(project_root, head_before, head_after),
                duration_sec=duration,
                stagnation=stagnation,
                returncode=result.returncode,
                session_id=session_id,
                stats=extract_result_stats(result.output),
                output_tail=_output_tail(result.output) if result.returncode != 0 else None,
            ),
        )

        if any(r.get("event") == "sprint_complete" and r.get("ref") == complete_ref for r in new):
            return EXIT_COMPLETE
        # Only a target-level circuit_open (orchestrator gave up on the whole
        # target, ref == target.ref) is terminal. Card-level breaks
        # (ref=<task-card>) mean "blocked this card, skip to the next" and must
        # NOT halt the loop — see references/unattended-overrides.md item 3.
        if any(r.get("event") == "circuit_open" and r.get("ref") == complete_ref for r in new):
            return EXIT_CIRCUIT

        if stagnation >= stagnation_threshold:
            _emit_circuit_open(project_root, target, f"stagnation: 连续 {stagnation} 轮无进展")
            return EXIT_CIRCUIT

    return EXIT_MAX_ITERATIONS
