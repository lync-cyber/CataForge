"""Unattended building-loop driver — in-process, cross-platform.

The loop is exercised end-to-end with an injected ``claude_runner`` (no live
``claude``) and no-op ``sleep`` (no wall-clock waits) over a real temp git
repo, so every exit path — complete / stagnation / rate-limit / cap /
pre-flight — is deterministic on any OS.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cataforge.core.event_log import append_event, build_record
from cataforge.runtime.unattended import (
    EXIT_CIRCUIT,
    EXIT_COMPLETE,
    EXIT_MAX_ITERATIONS,
    EXIT_PREFLIGHT,
    METRICS_FIELDS,
    METRICS_WAIT_FIELDS,
    UNATTENDED_ENV,
    ClaudeResult,
    build_prompt,
    extract_result_stats,
    extract_session_id,
    metrics_path,
    prototype_target,
    rate_limited,
    run_building_loop,
    sprint_target,
    transcript_path,
)

_SCHEMA = (
    Path(__file__).resolve().parents[2] / ".cataforge" / "schemas" / "loop-metrics.schema.json"
)

_NOOP = lambda _s: None  # noqa: E731 — injected sleep


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_repo(tmp_path: Path, branch: str) -> None:
    _git(tmp_path, "init", "-b", branch)
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "init")


def _loop(tmp_path: Path, runner, **overrides) -> int:
    kwargs = dict(
        max_iterations=5,
        stagnation_threshold=2,
        card_revision_ceiling=3,
        iter_timeout_sec=10.0,
        ratelimit_wait_sec=0.0,
        claude_runner=runner,
        sleep=_NOOP,
    )
    kwargs.update(overrides)
    return run_building_loop(tmp_path, sprint_target("sprint-1"), **kwargs)


def test_refuses_on_main(tmp_path: Path) -> None:
    _init_repo(tmp_path, "main")
    assert _loop(tmp_path, lambda p, t: ClaudeResult(0, "ok")) == EXIT_PREFLIGHT


def test_refuses_on_unborn_main(tmp_path: Path) -> None:
    # A freshly-init'd main with zero commits: `rev-parse --abbrev-ref HEAD`
    # fails there, but the fail-closed pre-flight (symbolic-ref) must still refuse.
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    assert _loop(tmp_path, lambda p, t: ClaudeResult(0, "ok")) == EXIT_PREFLIGHT


def test_completes_on_sprint_complete(tmp_path: Path) -> None:
    _init_repo(tmp_path, "feat-x")

    def runner(prompt: str, timeout: float) -> ClaudeResult:
        append_event(
            tmp_path,
            build_record(
                event="sprint_complete",
                phase="development",
                ref="dev-plan#sprint-1",
                detail="done",
            ),
        )
        return ClaudeResult(0, "ok")

    assert _loop(tmp_path, runner) == EXIT_COMPLETE


def test_stagnation_breaks_when_no_progress(tmp_path: Path) -> None:
    _init_repo(tmp_path, "feat-x")
    assert _loop(tmp_path, lambda p, t: ClaudeResult(0, "still thinking")) == EXIT_CIRCUIT


def test_churn_events_do_not_reset_stagnation(tmp_path: Path) -> None:
    _init_repo(tmp_path, "feat-x")

    def runner(prompt: str, timeout: float) -> ClaudeResult:
        # Bookkeeping / churn only: a needs_revision verdict + revision_start,
        # no commit, no forward-movement event → must count as stagnation.
        for ev in ("review_verdict", "revision_start"):
            append_event(
                tmp_path,
                build_record(event=ev, phase="development", ref="dev-plan#T-1", detail="churn"),
            )
        return ClaudeResult(0, "still spinning on the same card")

    # Two churn-only rounds must trip stagnation even though the event count
    # grows every round (churn events are not forward-movement events).
    assert _loop(tmp_path, runner, stagnation_threshold=2) == EXIT_CIRCUIT


def test_rate_limit_waits_then_retries_without_consuming_budget(tmp_path: Path) -> None:
    _init_repo(tmp_path, "feat-x")
    calls: list[int] = []

    def runner(prompt: str, timeout: float) -> ClaudeResult:
        calls.append(1)
        if len(calls) == 1:
            return ClaudeResult(1, '{"type":"error","error":{"type":"rate_limit_error"}}')
        append_event(
            tmp_path,
            build_record(
                event="sprint_complete",
                phase="development",
                ref="dev-plan#sprint-1",
                detail="done",
            ),
        )
        return ClaudeResult(0, "ok")

    assert _loop(tmp_path, runner, max_iterations=3) == EXIT_COMPLETE
    assert len(calls) == 2


def test_hits_iteration_cap(tmp_path: Path) -> None:
    _init_repo(tmp_path, "feat-x")

    def runner(prompt: str, timeout: float) -> ClaudeResult:
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "churn"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        return ClaudeResult(0, "progress but never done")

    # HEAD moves every round so stagnation never fires; only the cap bounds it.
    assert _loop(tmp_path, runner, max_iterations=3) == EXIT_MAX_ITERATIONS


def test_writes_metrics_line_per_real_iteration(tmp_path: Path) -> None:
    _init_repo(tmp_path, "feat-x")

    def runner(prompt: str, timeout: float) -> ClaudeResult:
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "churn"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        return ClaudeResult(0, "progress but never done")

    _loop(tmp_path, runner, max_iterations=2)

    lines = metrics_path(tmp_path).read_text().splitlines()
    assert len(lines) == 2
    for i, line in enumerate(lines, start=1):
        rec = json.loads(line)
        assert set(rec) == set(METRICS_FIELDS)
        assert rec["iter"] == i
        assert rec["progressed"] is True


def test_unattended_env_carries_marker_and_autonomous_identity() -> None:
    assert UNATTENDED_ENV["CATAFORGE_UNATTENDED"] == "1"
    assert UNATTENDED_ENV["GIT_AUTHOR_NAME"] == "cataforge-unattended"
    assert UNATTENDED_ENV["GIT_AUTHOR_EMAIL"] == "unattended@cataforge.local"
    assert UNATTENDED_ENV["GIT_COMMITTER_NAME"] == "cataforge-unattended"


def test_metrics_fields_match_schema() -> None:
    schema = json.loads(_SCHEMA.read_text())
    defs = schema["$defs"]
    assert set(defs["iteration"]["properties"]) == set(METRICS_FIELDS)
    assert set(defs["iteration"]["required"]) == set(METRICS_FIELDS)
    assert set(defs["wait"]["properties"]) == set(METRICS_WAIT_FIELDS)
    assert set(defs["wait"]["required"]) == set(METRICS_WAIT_FIELDS)


def test_card_level_circuit_open_does_not_halt_loop(tmp_path: Path) -> None:
    _init_repo(tmp_path, "feat-x")
    calls: list[int] = []

    def runner(prompt: str, timeout: float) -> ClaudeResult:
        # card-level break (ref = task card, not the sprint) → skip card, keep going
        calls.append(1)
        append_event(
            tmp_path,
            build_record(
                event="circuit_open",
                phase="development",
                ref="dev-plan#T-014",
                detail="card blocked, skip",
            ),
        )
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "churn"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        return ClaudeResult(0, "moved to next card")

    assert _loop(tmp_path, runner, max_iterations=2) == EXIT_MAX_ITERATIONS
    # Ran the full cap — the card-level break did not short-circuit the loop.
    assert len(calls) == 2


def test_sprint_level_circuit_open_halts_loop(tmp_path: Path) -> None:
    _init_repo(tmp_path, "feat-x")

    def runner(prompt: str, timeout: float) -> ClaudeResult:
        append_event(
            tmp_path,
            build_record(
                event="circuit_open",
                phase="development",
                ref="dev-plan#sprint-1",
                detail="gave up",
            ),
        )
        return ClaudeResult(0, "ok")

    assert _loop(tmp_path, runner) == EXIT_CIRCUIT


def test_rc_zero_output_mentioning_limit_is_not_a_wait(tmp_path: Path) -> None:
    _init_repo(tmp_path, "feat-x")
    calls: list[int] = []

    def runner(prompt: str, timeout: float) -> ClaudeResult:
        calls.append(1)
        append_event(
            tmp_path,
            build_record(
                event="sprint_complete",
                phase="development",
                ref="dev-plan#sprint-1",
                detail="done",
            ),
        )
        return ClaudeResult(0, "I fixed the rate_limit_error handler")

    assert _loop(tmp_path, runner) == EXIT_COMPLETE
    assert len(calls) == 1


def test_consecutive_waits_hit_cap(tmp_path: Path) -> None:
    _init_repo(tmp_path, "feat-x")
    calls: list[int] = []

    def runner(prompt: str, timeout: float) -> ClaudeResult:
        calls.append(1)
        return ClaudeResult(1, "overloaded_error")

    assert _loop(tmp_path, runner, max_iterations=3) == EXIT_MAX_ITERATIONS
    assert len(calls) == 3


def test_rate_limited_detects_error_type_not_prose() -> None:
    assert rate_limited('{"type":"error","error":{"type":"rate_limit_error"}}')
    assert rate_limited("overloaded_error")
    assert not rate_limited("I refactored the rate-limiting middleware")
    assert not rate_limited('{"type":"result","ok":true}')


def test_prototype_target_completes_on_brief_tasks_ref(tmp_path: Path) -> None:
    # agile-prototype has no sprint grouping: the completion contract keys on
    # ref=brief#tasks, so a dev-plan#sprint sprint_complete must NOT complete it.
    _init_repo(tmp_path, "feat-x")

    def runner(prompt: str, timeout: float) -> ClaudeResult:
        append_event(
            tmp_path,
            build_record(
                event="sprint_complete", phase="development", ref="brief#tasks", detail="d"
            ),
        )
        return ClaudeResult(0, "ok")

    kwargs = dict(
        max_iterations=5,
        stagnation_threshold=2,
        card_revision_ceiling=3,
        iter_timeout_sec=10.0,
        ratelimit_wait_sec=0.0,
        claude_runner=runner,
        sleep=_NOOP,
    )
    assert run_building_loop(tmp_path, prototype_target(), **kwargs) == EXIT_COMPLETE


def test_prototype_target_stagnation_emits_brief_tasks_ref(tmp_path: Path) -> None:
    _init_repo(tmp_path, "feat-x")
    kwargs = dict(
        max_iterations=5,
        stagnation_threshold=2,
        card_revision_ceiling=3,
        iter_timeout_sec=10.0,
        ratelimit_wait_sec=0.0,
        claude_runner=lambda p, t: ClaudeResult(0, "spinning"),
        sleep=_NOOP,
    )
    assert run_building_loop(tmp_path, prototype_target(), **kwargs) == EXIT_CIRCUIT
    from cataforge.core.event_log import event_log_path

    lines = event_log_path(tmp_path).read_text(encoding="utf-8").splitlines()
    breaker = [json.loads(ln) for ln in lines if '"circuit_open"' in ln]
    assert breaker and breaker[-1]["ref"] == "brief#tasks"


def test_build_prompt_is_target_aware() -> None:
    sprint = build_prompt(sprint_target("sprint-2"), 3)
    assert "dev-plan#sprint-2" in sprint and "brief" not in sprint

    proto = build_prompt(prototype_target(), 3)
    assert "brief#tasks" in proto
    assert "dev-plan" not in proto
    assert "brief" in proto
    # Card-level breaks must use the task-card id, never brief#tasks — else the
    # shell mistakes the first card break for a whole-target circuit and exits.
    assert "该任务卡 id" in proto


def _complete(tmp_path: Path, ref: str = "dev-plan#sprint-1") -> None:
    append_event(
        tmp_path,
        build_record(event="sprint_complete", phase="development", ref=ref, detail="done"),
    )


def _metrics_records(tmp_path: Path) -> list[dict]:
    return [json.loads(ln) for ln in metrics_path(tmp_path).read_text().splitlines()]


def test_timeout_wait_writes_wait_record_and_skips_sleep(tmp_path: Path) -> None:
    # A timeout kill is not a rate limit: it must be visible in the metrics
    # stream (kind=wait, reason=timeout) and must NOT burn a cooldown sleep.
    _init_repo(tmp_path, "feat-x")
    calls: list[int] = []
    sleeps: list[float] = []

    def runner(prompt: str, limits) -> ClaudeResult:
        calls.append(1)
        if len(calls) == 1:
            return ClaudeResult(
                _TIMEOUT_RC_TEST, "partial output", timed_out=True, timeout_reason="silence"
            )
        _complete(tmp_path)
        return ClaudeResult(0, "ok")

    assert _loop(tmp_path, runner, ratelimit_wait_sec=300.0, sleep=sleeps.append) == EXIT_COMPLETE
    assert sleeps == []  # timeout kill skips the rate-limit cooldown
    waits = [r for r in _metrics_records(tmp_path) if r["kind"] == "wait"]
    assert len(waits) == 1
    assert waits[0]["reason"] == "timeout"
    assert waits[0]["timeout_reason"] == "silence"
    assert waits[0]["consecutive_waits"] == 1


def test_rate_limit_wait_writes_wait_record_and_sleeps(tmp_path: Path) -> None:
    _init_repo(tmp_path, "feat-x")
    calls: list[int] = []
    sleeps: list[float] = []

    def runner(prompt: str, limits) -> ClaudeResult:
        calls.append(1)
        if len(calls) == 1:
            return ClaudeResult(1, "overloaded_error")
        _complete(tmp_path)
        return ClaudeResult(0, "ok")

    assert _loop(tmp_path, runner, ratelimit_wait_sec=300.0, sleep=sleeps.append) == EXIT_COMPLETE
    assert sleeps == [300.0]
    waits = [r for r in _metrics_records(tmp_path) if r["kind"] == "wait"]
    assert len(waits) == 1 and waits[0]["reason"] == "rate_limit"
    assert waits[0]["timeout_reason"] is None


def test_timeout_with_head_move_resets_consecutive_waits(tmp_path: Path) -> None:
    # A killed session that still committed made real progress: the wait
    # counter must reset, or a long-tail card would trip EXIT_MAX_ITERATIONS
    # while the sprint is genuinely advancing.
    _init_repo(tmp_path, "feat-x")
    calls: list[int] = []

    def runner(prompt: str, limits) -> ClaudeResult:
        calls.append(1)
        if len(calls) <= 2:
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "progress"],
                cwd=tmp_path,
                check=True,
                capture_output=True,
            )
            return ClaudeResult(_TIMEOUT_RC_TEST, "", timed_out=True, timeout_reason="total")
        _complete(tmp_path)
        return ClaudeResult(0, "ok")

    # max_iterations=2: without the head-moved reset, two consecutive timeout
    # waits would exhaust the wait cap before the third (completing) round.
    assert _loop(tmp_path, runner, max_iterations=2) == EXIT_COMPLETE
    assert len(calls) == 3
    waits = [r for r in _metrics_records(tmp_path) if r["kind"] == "wait"]
    assert [w["head_moved"] for w in waits] == [True, True]
    assert [w["consecutive_waits"] for w in waits] == [0, 0]


def test_terminal_round_writes_metrics(tmp_path: Path) -> None:
    # sprint_complete / circuit_open rounds previously returned before the
    # metrics append — the whole run could finish with zero records.
    _init_repo(tmp_path, "feat-x")

    def runner(prompt: str, limits) -> ClaudeResult:
        _complete(tmp_path)
        return ClaudeResult(0, "ok")

    assert _loop(tmp_path, runner) == EXIT_COMPLETE
    recs = _metrics_records(tmp_path)
    assert len(recs) == 1 and recs[0]["kind"] == "iteration"


def test_failed_round_records_returncode_and_output_tail(tmp_path: Path) -> None:
    # A non-zero exit that is not a rate limit (auth failure, CLI crash) must
    # be distinguishable from an idle round after the fact.
    _init_repo(tmp_path, "feat-x")
    calls: list[int] = []

    def runner(prompt: str, limits) -> ClaudeResult:
        calls.append(1)
        if len(calls) == 1:
            return ClaudeResult(2, "fatal: authentication failed")
        _complete(tmp_path)
        return ClaudeResult(0, "ok")

    assert _loop(tmp_path, runner) == EXIT_COMPLETE
    failed = [r for r in _metrics_records(tmp_path) if r["returncode"] == 2]
    assert len(failed) == 1
    assert "authentication failed" in failed[0]["output_tail"]
    ok = [r for r in _metrics_records(tmp_path) if r["returncode"] == 0]
    assert ok and ok[0]["output_tail"] is None


def test_transcript_persisted_and_session_id_extracted(tmp_path: Path) -> None:
    _init_repo(tmp_path, "feat-x")
    stream = (
        '{"type":"system","subtype":"init","session_id":"abc-123"}\n'
        '{"type":"result","subtype":"success","total_cost_usd":1.25,'
        '"usage":{"input_tokens":10,"output_tokens":20,"cache_read_input_tokens":300}}'
    )

    def runner(prompt: str, limits) -> ClaudeResult:
        _complete(tmp_path)
        return ClaudeResult(0, stream)

    assert _loop(tmp_path, runner) == EXIT_COMPLETE
    saved = transcript_path(tmp_path, 1)
    assert saved.is_file() and "abc-123" in saved.read_text(encoding="utf-8")
    rec = _metrics_records(tmp_path)[0]
    assert rec["session_id"] == "abc-123"
    assert rec["tokens_in"] == 10 and rec["tokens_out"] == 20
    assert rec["cache_read_tokens"] == 300 and rec["cost_usd"] == 1.25


def test_loop_passes_incrementing_attempt_to_runner(tmp_path: Path) -> None:
    # attempt numbers every launch (waits included) — it keys the transcript
    # file and the CATAFORGE_UNATTENDED_ITER correlation env var.
    _init_repo(tmp_path, "feat-x")
    attempts: list[int] = []

    def runner(prompt: str, limits) -> ClaudeResult:
        attempts.append(limits.attempt)
        if len(attempts) == 1:
            return ClaudeResult(1, "overloaded_error")
        _complete(tmp_path)
        return ClaudeResult(0, "ok")

    assert _loop(tmp_path, runner) == EXIT_COMPLETE
    assert attempts == [1, 2]


def test_extract_session_id_and_result_stats() -> None:
    out = (
        'noise\n{"type":"system","subtype":"init","session_id":"s-1"}\n'
        '{"type":"result","total_cost_usd":0.5,"usage":{"input_tokens":1,"output_tokens":2}}'
    )
    assert extract_session_id(out) == "s-1"
    stats = extract_result_stats(out)
    assert stats["tokens_in"] == 1 and stats["tokens_out"] == 2
    assert stats["cost_usd"] == 0.5 and stats["cache_read_tokens"] is None
    # Garbage in → all-None out, never a raise.
    empty = extract_result_stats("not json at all")
    assert set(empty) == {"tokens_in", "tokens_out", "cache_read_tokens", "cost_usd"}
    assert all(v is None for v in empty.values())
    assert extract_session_id("") is None


def test_build_prompt_declares_unit_of_work_and_budget() -> None:
    # #480: sessions must be told to finish one card then exit cleanly, and to
    # converge to a committable state when nearing the session budget.
    for prompt in (
        build_prompt(sprint_target("sprint-2"), 3, session_budget_min=180),
        build_prompt(prototype_target(), 3, session_budget_min=180),
    ):
        assert "最多完成一张任务卡" in prompt
        assert "180 分钟" in prompt
    # No budget → no budget sentence, unit-of-work rule stays.
    no_budget = build_prompt(sprint_target("sprint-2"), 3)
    assert "分钟" not in no_budget and "最多完成一张任务卡" in no_budget


_TIMEOUT_RC_TEST = 124


def test_rate_limited_matches_subscription_cap_phrasings() -> None:
    # The CLI's own subscription-cap messages (space-separated, not the API's
    # snake_case error types) must also count as a wait, not a hard failure.
    assert rate_limited("Claude AI usage limit reached")
    assert rate_limited("5-hour limit reached")
    assert rate_limited("weekly limit reached")
    # Still no false positive on hyphenated prose (no space/underscore form).
    assert not rate_limited("tuned the rate-limiting middleware")
    # A bare "limit reached" without a rate/usage qualifier is an unrelated hard
    # failure, not a rate-limit wait — must not burn a 300s auto-wait on it.
    assert not rate_limited("max retries limit reached, giving up")
    assert not rate_limited("connection pool limit reached")
