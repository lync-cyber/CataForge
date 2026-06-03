"""The UTF-8 relaunch in tests/conftest.py must mirror the child session's
exit code, not crash pytest's main loop.

In a non-UTF-8 locale without ``PYTHONUTF8``, ``conftest`` relaunches the
session under ``PYTHONUTF8=1`` (on win32 via a subprocess). The launcher must
then exit with the child's return code. A ``SystemExit`` raised from
``pytest_configure`` is caught by pytest and reported as INTERNALERROR
(exit 3), masking a clean child run — which made the ``stdio-utf8-guard``
pre-commit hook fail on every ``scripts/*.py`` commit on Windows.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_utf8_relaunch_mirrors_child_exit_code() -> None:
    env = os.environ.copy()
    # Force the relaunch branch: clear the re-exec sentinel and pin a non-UTF-8
    # default encoding. PYTHONUTF8=0 turns UTF-8 Mode off and
    # PYTHONCOERCECLOCALE=0 stops PEP 538 from coercing C → C.UTF-8, so
    # locale.getpreferredencoding() is ascii on POSIX (cp9xx on Windows) —
    # exactly the condition conftest relaunches under.
    env.pop("_CATAFORGE_TEST_UTF8_REEXEC", None)
    env["PYTHONUTF8"] = "0"
    env["PYTHONCOERCECLOCALE"] = "0"
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env["CATAFORGE_SKIP_HOOK_AUTOINSTALL"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_scripts_stdio_guard.py",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    combined = result.stdout + result.stderr

    assert "INTERNALERROR" not in combined, combined
    assert "caught unexpected SystemExit" not in combined, combined
    assert result.returncode == 0, f"rc={result.returncode}\n{combined}"
