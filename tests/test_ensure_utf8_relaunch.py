"""Guard: ``ensure_utf8`` forces a UTF-8 default file encoding even under a
non-UTF-8 locale, by relaunching the interpreter in Python UTF-8 Mode.

stdout/stderr are reconfigured unconditionally, but ``open()`` /
``read_text()`` default encoding follows ``locale.getpreferredencoding``
unless the interpreter runs in UTF-8 Mode. Under ``LC_ALL=C`` that default
is ASCII, so bare file I/O would mis-decode UTF-8. The relaunch sets
``PYTHONUTF8=1`` and replaces the process image so the default becomes UTF-8.

The relaunch is suppressed under pytest, so this test drives it from a child
``python -c`` with ``PYTEST_*`` stripped and ``PYTHONUTF8`` unset.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX os.execve path; the Windows relaunch is covered by the console-script e2e suite",
)

# Import the helper, call it, then report whether the (re-execed) process
# ended up in UTF-8 Mode and what ``open()`` defaults to. ASCII-only output
# so the parent's capture decode can never be the thing under test.
_PROBE = (
    "from cataforge.utils.common import ensure_utf8; ensure_utf8(); "
    "import os, sys; "
    "f = open(os.devnull); "
    "print('utf8_mode=' + str(int(sys.flags.utf8_mode))); "
    "print('open_enc=' + (f.encoding or 'none').lower()); "
    "f.close()"
)


def test_ensure_utf8_relaunches_into_utf8_mode_under_c_locale() -> None:
    env = os.environ.copy()
    env.pop("PYTHONUTF8", None)
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    for key in list(env):
        if key.startswith("PYTEST_"):
            del env[key]

    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "utf8_mode=1" in proc.stdout, proc.stdout + proc.stderr
    assert "open_enc=utf-8" in proc.stdout, proc.stdout + proc.stderr
