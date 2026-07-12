"""Stream-silence supervision — exercised against a real child process."""

from __future__ import annotations

import sys
from pathlib import Path

from cataforge.runtime.unattended import IterLimits, run_streaming

_PY = sys.executable


def _limits(tmp_path: Path, silence: float, total: float) -> IterLimits:
    return IterLimits(
        silence_timeout_sec=silence,
        total_timeout_sec=total,
        transcript_path=tmp_path / "iter-001.jsonl",
        attempt=1,
    )


def test_clean_exit_is_not_killed(tmp_path: Path) -> None:
    code = 'print(\'{"type":"system","session_id":"s-1"}\')'
    result = run_streaming([_PY, "-c", code], _limits(tmp_path, 30.0, 60.0), env=None)
    assert result.returncode == 0 and not result.timed_out
    assert "s-1" in result.output
    # The transcript was streamed to disk, not reconstructed post-mortem.
    assert "s-1" in (tmp_path / "iter-001.jsonl").read_text(encoding="utf-8")


def test_silent_hang_is_killed_with_partial_output(tmp_path: Path) -> None:
    # One heartbeat line, then a hang far longer than the silence budget: the
    # supervisor must kill on silence and still hand back the partial stream.
    code = 'import sys, time; print("alive"); sys.stdout.flush(); time.sleep(120)'
    result = run_streaming([_PY, "-c", code], _limits(tmp_path, 1.0, 60.0), env=None)
    assert result.timed_out and result.timeout_reason == "silence"
    assert "alive" in result.output
    assert "alive" in (tmp_path / "iter-001.jsonl").read_text(encoding="utf-8")


def test_steady_output_hits_total_backstop_not_silence(tmp_path: Path) -> None:
    # A pathological session that never stops emitting must be bounded by the
    # loose total backstop, never by the silence criterion.
    code = "import sys, time\nwhile True:\n    print('tick'); sys.stdout.flush(); time.sleep(0.2)"
    result = run_streaming([_PY, "-c", code], _limits(tmp_path, 30.0, 2.0), env=None)
    assert result.timed_out and result.timeout_reason == "total"
    assert "tick" in result.output


def test_missing_executable_reports_127(tmp_path: Path) -> None:
    result = run_streaming(
        ["definitely-not-a-real-binary-xyz"], _limits(tmp_path, 1.0, 2.0), env=None
    )
    assert result.returncode == 127 and "not found" in result.output
