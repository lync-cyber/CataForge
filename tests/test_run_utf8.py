"""Regression guard for the shared ``run_utf8`` subprocess helper.

If this test ever starts failing on Windows, someone has likely removed
the explicit ``encoding="utf-8"`` from
:func:`tests.conftest.run_utf8` — that change re-opens the cp1252 trap
where ``CompletedProcess.stdout`` silently becomes ``None`` whenever a
child process emits non-ASCII output (Chinese prose, em-dashes,
box-drawing). Don't "simplify" the helper without first replacing this
guard.
"""

from __future__ import annotations

import sys

import pytest

from tests.conftest import run_utf8

# A short Python program that writes Chinese + em-dash bytes to stdout.
# Crashes the parent's reader thread under cp1252 if encoding isn't
# explicit — symptom is r.stdout == None.
_UTF8_PROGRAM = (
    "import sys; "
    "sys.stdout.buffer.write('结果: PASS — 中文 ✓\\n'.encode('utf-8'))"
)


def test_run_utf8_decodes_non_ascii_stdout() -> None:
    r = run_utf8([sys.executable, "-c", _UTF8_PROGRAM])
    assert r.returncode == 0, r.stderr
    # Without encoding="utf-8" + errors="replace", this is None on
    # Windows + cp1252.
    assert r.stdout is not None
    assert "结果: PASS" in r.stdout
    assert "中文" in r.stdout


def test_run_utf8_pythonutf8_env_set_in_child() -> None:
    r = run_utf8(
        [sys.executable, "-c",
         "import os; print(os.environ.get('PYTHONUTF8', 'unset'))"]
    )
    assert r.returncode == 0
    assert r.stdout.strip() == "1"


def test_run_utf8_extra_env_merges() -> None:
    r = run_utf8(
        [sys.executable, "-c",
         "import os; print(os.environ.get('CATAFORGE_TEST_VAR', 'missing'))"],
        extra_env={"CATAFORGE_TEST_VAR": "ok"},
    )
    assert r.returncode == 0
    assert r.stdout.strip() == "ok"


def test_run_utf8_check_raises_on_nonzero() -> None:
    import subprocess
    with pytest.raises(subprocess.CalledProcessError):
        run_utf8([sys.executable, "-c", "import sys; sys.exit(7)"], check=True)


def test_run_utf8_no_check_returns_nonzero() -> None:
    r = run_utf8([sys.executable, "-c", "import sys; sys.exit(7)"])
    assert r.returncode == 7
