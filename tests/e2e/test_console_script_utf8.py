"""End-to-end: the installed ``cataforge`` console script runs cleanly.

The rest of the e2e suite invokes ``python -m cataforge`` (see
``run_cataforge`` in conftest) and the unit suite uses in-process
``CliRunner`` — neither path touches the console-script launcher, and
both run with ``PYTHONUTF8=1`` and ``PYTEST_*`` set in the environment.
That combination structurally disables ``ensure_utf8()``'s Windows
relaunch branch, so a launcher-only regression in that branch ships
invisibly.

These tests close that gap: they run the real ``cataforge`` executable
(a zipapp-style launcher, where ``__main__.__spec__.name == "__main__"``)
with ``PYTHONUTF8`` unset and every ``PYTEST_*`` var stripped, so on
Windows the relaunch branch actually fires. A broken relaunch target or
a crashing relaunch mechanism surfaces here as a non-zero exit / empty
output / traceback.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow


def _console_script(py_exe: Path) -> Path:
    """Locate the ``cataforge`` console script next to the venv python."""
    scripts_dir = py_exe.parent
    exe = scripts_dir / ("cataforge.exe" if os.name == "nt" else "cataforge")
    assert exe.is_file(), f"console script not found at {exe}"
    return exe


def _run_launcher(py_exe: Path, *args: str, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    """Run the console script with a UTF-8-relaunch-enabling environment.

    Strips ``PYTHONUTF8`` and all ``PYTEST_*`` vars so the child's
    ``ensure_utf8()`` takes the Windows relaunch path instead of
    short-circuiting. Captures raw bytes (no parent-side text decoding)
    so the test, not the parent's locale, owns the UTF-8 decode.
    """
    env = os.environ.copy()
    env.pop("PYTHONUTF8", None)
    for key in list(env):
        if key.startswith("PYTEST_"):
            del env[key]
    return subprocess.run(
        [str(_console_script(py_exe)), *args],
        cwd=str(cwd),
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
    )


def _text(proc: subprocess.CompletedProcess[bytes]) -> str:
    return proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")


def test_console_script_version_runs(cataforge_venv: Path, tmp_path: Path) -> None:
    proc = _run_launcher(cataforge_venv, "--version", cwd=tmp_path)
    out = _text(proc)
    assert proc.returncode == 0, out
    assert "cataforge" in out.lower()
    assert "Traceback" not in out
    # The original launcher bug surfaced as this exact message on stderr.
    assert "__spec__ is None" not in out


def test_console_script_help_runs(cataforge_venv: Path, tmp_path: Path) -> None:
    """``--help`` emits a full help page — the high-output command that
    crashed the ``os.exec*``-based relaunch with an access violation."""
    proc = _run_launcher(cataforge_venv, "--help", cwd=tmp_path)
    out = _text(proc)
    assert proc.returncode == 0, out
    assert proc.stdout, "no stdout — relaunch likely crashed before printing"
    assert "Usage:" in out and "bootstrap" in out
    assert "Traceback" not in out


def test_console_script_non_ascii_renders(cataforge_venv: Path, tmp_path: Path) -> None:
    """Chinese output must survive the relaunch + UTF-8 reconfigure without a
    UnicodeEncodeError traceback. ``hook list`` prints Chinese hook
    descriptions (e.g. 危险命令拦截) once the project is scaffolded."""
    scaffold = _run_launcher(cataforge_venv, "setup", "--no-deploy", cwd=tmp_path)
    assert scaffold.returncode == 0, _text(scaffold)

    proc = _run_launcher(cataforge_venv, "hook", "list", cwd=tmp_path)
    out = _text(proc)
    assert proc.returncode == 0, out
    assert "Traceback" not in out
    assert any("一" <= c <= "鿿" for c in out)
