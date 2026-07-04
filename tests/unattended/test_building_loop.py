"""Unattended building-loop driver — in-process, cross-platform.

The loop is exercised end-to-end with an injected ``claude_runner`` (no live
``claude``) and no-op ``sleep`` (no wall-clock waits) over a real temp git
repo, so every exit path — complete / stagnation / same-error / rate-limit /
cap / pre-flight — is deterministic on any OS.
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
    error_signature,
    metrics_path,
    rate_limited,
    run_building_loop,
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
        same_error_ceiling=2,
        iter_timeout_sec=10.0,
        ratelimit_wait_sec=0.0,
        claude_runner=runner,
        sleep=_NOOP,
    )
    kwargs.update(overrides)
    return run_building_loop(tmp_path, "sprint-1", **kwargs)


def test_refuses_on_main(tmp_path: Path) -> None:
    _init_repo(tmp_path, "main")
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


def test_same_error_breaks_even_when_head_moves(tmp_path: Path) -> None:
    _init_repo(tmp_path, "feat-x")

    def runner(prompt: str, timeout: float) -> ClaudeResult:
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "churn"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        return ClaudeResult(0, "TypeError: cannot frobnicate the widget")

    # HEAD advances each round so stagnation resets; only same-error can fire.
    assert _loop(tmp_path, runner, stagnation_threshold=99) == EXIT_CIRCUIT


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

    assert _loop(tmp_path, runner, max_iterations=3, same_error_ceiling=99) == EXIT_MAX_ITERATIONS


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

    _loop(tmp_path, runner, max_iterations=2, same_error_ceiling=99)

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

    assert _loop(tmp_path, runner, max_iterations=2, same_error_ceiling=99) == EXIT_MAX_ITERATIONS
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


def test_error_signature_stable_across_volatile_frames() -> None:
    a = error_signature('File "/abs/path/mod.py", line 42, in f\nAssertionError: boom')
    b = error_signature('File "/other/path/mod.py", line 99, in f\nAssertionError: boom')
    assert a == b
    assert a != ""


def test_error_signature_distinguishes_different_operands() -> None:
    a = error_signature("AssertionError: assert 3 == 4")
    b = error_signature("AssertionError: assert 7 == 9")
    assert a != b


def test_rate_limited_detects_error_type_not_prose() -> None:
    assert rate_limited('{"type":"error","error":{"type":"rate_limit_error"}}')
    assert rate_limited("overloaded_error")
    assert not rate_limited("I refactored the rate-limiting middleware")
    assert not rate_limited('{"type":"result","ok":true}')


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


def test_refuses_on_unborn_main(tmp_path: Path) -> None:
    # A freshly-init'd main with zero commits: `rev-parse --abbrev-ref HEAD`
    # fails there, but the fail-closed pre-flight must still refuse.
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    assert _loop(tmp_path, lambda p, t: ClaudeResult(0, "ok")) == EXIT_PREFLIGHT


def test_error_signature_ignores_prose_and_summary_lines() -> None:
    # Prose mentioning "error"/"failed" and a pytest summary line (whose volatile
    # duration would otherwise defeat folding) must NOT become the signature.
    a = error_signature(
        "I fixed the error-handling path\n"
        '  File "/repo/mod.py", line 5\n'
        "TypeError: bad thing\n"
        "===== 1 failed in 3.20s ====="
    )
    b = error_signature(
        "discussing error handling again\n"
        '  File "/other/mod.py", line 91\n'
        "TypeError: bad thing\n"
        "===== 1 failed in 9.87s ====="
    )
    assert a == b != ""


def test_error_signature_folds_real_pytest_bare_assert() -> None:
    # Real pytest output for a bare `assert` failure carries no "AssertionError:"
    # token — only `E   assert …`, `path:lineno: AssertionError` (colon *before*
    # the type), and the `FAILED <nodeid> - <msg>` summary. The signature must
    # still be non-empty and fold across a changing run duration.
    r1 = (
        "    def test_x():\n"
        ">       assert 1 == 2\n"
        "E       assert 1 == 2\n"
        "test_demo.py:2: AssertionError\n"
        "FAILED test_demo.py::test_x - assert 1 == 2\n"
        "1 failed in 0.09s"
    )
    r2 = r1.replace("0.09s", "4.55s")
    assert error_signature(r1) == error_signature(r2) != ""
    # A different assertion must NOT fold into the same signature.
    r3 = r1.replace("1 == 2", "3 == 9")
    assert error_signature(r1) != error_signature(r3)


def test_error_signature_folds_over_stream_json_records() -> None:
    # The live runner captures `--output-format stream-json`: pytest output is
    # embedded + newline-escaped inside one JSON record with a per-run session
    # id. The same failure across two such records must fold to one signature.
    out = "E       assert 1 == 2\nFAILED test_demo.py::test_x - assert 1 == 2\n1 failed in 0.09s"
    rec1 = json.dumps({"type": "user", "session_id": "s-111", "message": {"content": out}})
    rec2 = json.dumps(
        {
            "type": "user",
            "session_id": "s-999",
            "message": {"content": out.replace("0.09s", "2.30s")},
        }
    )
    assert error_signature(rec1) == error_signature(rec2) != ""


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

    # stagnation_threshold=2 → two churn-only rounds must trip the breaker,
    # even though the event count grows every round.
    assert _loop(tmp_path, runner, stagnation_threshold=2, same_error_ceiling=99) == EXIT_CIRCUIT
