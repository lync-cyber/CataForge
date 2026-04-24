"""Shared fixtures for end-to-end tests.

These tests exercise the *real* user install path: build a wheel, create a
fresh venv, ``pip install`` the wheel, and invoke ``cataforge`` via
subprocess — the same thing a user types in their terminal.

The fixtures here are session-scoped because building a wheel is expensive
(~20-30s including the scaffold-sync hatch hook). Building once and
reusing across tests keeps a full e2e run under a minute.
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the current tree into a wheel and return its path.

    Runs the hatch build hook (which syncs the scaffold mirror) so the
    wheel ships with the exact ``.cataforge/`` layout the repo declares.
    """
    dist = tmp_path_factory.mktemp("dist")
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = sorted(dist.glob("cataforge-*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel in {dist}, got {wheels}"
    return wheels[0]


def make_venv(root: Path) -> Path:
    """Create an isolated venv at *root* and return its python executable."""
    venv.create(root, with_pip=True, clear=True, symlinks=(os.name != "nt"))
    if os.name == "nt":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def pip_install(py_exe: Path, *args: str) -> None:
    """Run ``<py_exe> -m pip install --quiet <args>`` with a non-interactive env."""
    subprocess.run(
        [str(py_exe), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def run_cataforge(
    py_exe: Path,
    *args: str,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Invoke ``<py_exe> -m cataforge <args>`` in *cwd*, capturing output.

    We invoke via ``-m cataforge`` rather than the ``cataforge`` console
    script so the test doesn't depend on the venv's Scripts/ directory
    being on PATH — matters on Windows where activating a venv inside
    subprocess is awkward.
    """
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [str(py_exe), "-m", "cataforge", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
