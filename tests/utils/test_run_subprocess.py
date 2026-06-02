"""Tests for ``cataforge.utils.run_subprocess.run``.

The wrapper's whole point is *consistency*: every call site gets the
same defaults. These tests pin the contract — if the defaults change
under us, every dependent migration would need to be reviewed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from cataforge.utils.run_subprocess import DEFAULT_TIMEOUT_SECONDS, run


class TestRunContract:
    def test_captures_stdout_by_default(self) -> None:
        result = run([sys.executable, "-c", "print('hello-from-child')"])
        assert result.returncode == 0
        assert "hello-from-child" in result.stdout
        assert result.stderr == ""

    def test_captures_stderr_separately(self) -> None:
        result = run([sys.executable, "-c", "import sys; sys.stderr.write('boom\\n')"])
        assert result.returncode == 0
        assert "boom" in result.stderr
        assert result.stdout == ""

    def test_returns_nonzero_returncode_without_raising(self) -> None:
        """``check=False`` is hard-coded: caller decides what non-zero means."""
        result = run([sys.executable, "-c", "import sys; sys.exit(7)"])
        assert result.returncode == 7
        # Crucially: did not raise CalledProcessError.

    def test_passes_stdin_via_input(self) -> None:
        result = run(
            [sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"],
            input="lowercase",
        )
        assert result.returncode == 0
        assert "LOWERCASE" in result.stdout

    def test_text_mode_is_default(self) -> None:
        """``text=True`` + ``encoding=utf-8`` is the default so the
        wrapper decodes output as utf-8 regardless of locale. We force
        the child to emit utf-8 bytes (its own stdout encoding follows
        the OS locale otherwise — cp1252 on a default Windows box) so
        the assertion exercises the wrapper's decoder, not the child's
        encoder."""
        result = run(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write('café\\n'.encode('utf-8'))",
            ]
        )
        assert isinstance(result.stdout, str)
        assert "café" in result.stdout

    def test_capture_output_false_streams_to_terminal(
        self, capfd: pytest.CaptureFixture[str]
    ) -> None:
        """Pass ``capture_output=False`` to let the child's stdout/stderr
        flow to the parent's tty (used for interactive helpers like
        ``git fetch`` whose progress lines belong in the user's terminal)."""
        result = run([sys.executable, "-c", "print('streamed')"], capture_output=False)
        assert result.returncode == 0
        # stdout was streamed, not captured into result.
        assert result.stdout is None
        captured = capfd.readouterr()
        assert "streamed" in captured.out

    def test_cwd_path_object_accepted(self, tmp_path: Path) -> None:
        result = run([sys.executable, "-c", "import os; print(os.getcwd())"], cwd=tmp_path)
        assert result.returncode == 0
        assert str(tmp_path.resolve()) in Path(result.stdout.strip()).resolve().as_posix() or (
            Path(result.stdout.strip()).resolve() == tmp_path.resolve()
        )

    def test_timeout_default_is_60_seconds(self) -> None:
        """Pin the default so future tweaks come through a deliberate
        ``DEFAULT_TIMEOUT_SECONDS`` change rather than silent drift."""
        assert DEFAULT_TIMEOUT_SECONDS == 60.0

    def test_timeout_raises_subprocess_timeoutexpired(self) -> None:
        """``TimeoutExpired`` still propagates so callers can decide
        between diagnose-and-continue and abort."""
        with pytest.raises(subprocess.TimeoutExpired):
            run(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                timeout=0.5,
            )

    def test_filenotfound_propagates(self) -> None:
        """Binary not on PATH still raises so the caller can give an
        actionable message rather than getting a generic non-zero exit."""
        with pytest.raises(FileNotFoundError):
            run(["definitely-not-a-real-binary-cataforge-test"])
