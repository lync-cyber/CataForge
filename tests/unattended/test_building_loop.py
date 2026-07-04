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


def test_error_signature_stable_across_volatile_frames() -> None:
    a = error_signature('File "/abs/path/mod.py", line 42, in f\nAssertionError: boom')
    b = error_signature('File "/other/path/mod.py", line 99, in f\nAssertionError: boom')
    assert a == b
    assert a != ""


def test_rate_limited_detects_signal_not_prose() -> None:
    assert rate_limited('{"type":"error","error":{"type":"rate_limit_error"}}')
    assert rate_limited("Error: overloaded, please retry")
    assert not rate_limited('{"type":"result","ok":true}')
