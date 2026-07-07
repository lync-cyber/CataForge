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
    UNATTENDED_ENV,
    ClaudeResult,
    build_prompt,
    metrics_path,
    prototype_target,
    rate_limited,
    run_building_loop,
    sprint_target,
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
    assert set(schema["properties"]) == set(METRICS_FIELDS)
    assert set(schema["required"]) == set(METRICS_FIELDS)


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
