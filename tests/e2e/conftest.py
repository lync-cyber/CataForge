"""Shared fixtures for end-to-end tests.

These tests exercise the *real* user install path: build a wheel, create a
venv, ``pip install`` the wheel, and invoke ``cataforge`` via subprocess —
the same thing a user types in their terminal.

Speed design: both the wheel build and the "venv + wheel installed"
steps are **session-scoped**, so every test in ``tests/e2e/`` that uses
the current package version shares one venv. Each test still gets its
own ``tmp_path`` for the project directory, so state is isolated; only
the Python environment is shared. Tests that need a different package
version (e.g. ``test_cross_version_upgrade``) must create their own
venv via :func:`make_venv` inside the test body.

Local timing reference (Windows 11, warm pip cache):
  - Before session-scoped venv: ~300s for 4 tests
  - After:                      ~70s for 4 tests (venv + install cost
                                paid once; individual tests only cover
                                scaffold/CLI work)
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

from tests.conftest import run_utf8

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the current tree into a wheel and return its path.

    Uses ``python -m build --wheel`` in isolated build mode — more
    portable across host Python distributions (e.g. Windows Store
    Python, where ``--no-isolation`` fails to resolve ``hatchling``
    because the host env doesn't carry it). The wheel packages
    ``.cataforge/`` directly via hatch ``force-include`` (no mirror
    sync step needed since PR #84).
    """
    dist = tmp_path_factory.mktemp("dist")
    run_utf8(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist)],
        cwd=REPO_ROOT,
        check=True,
        timeout=300,
    )
    wheels = sorted(dist.glob("cataforge-*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel in {dist}, got {wheels}"
    return wheels[0]


@pytest.fixture(scope="session")
def cataforge_venv(
    tmp_path_factory: pytest.TempPathFactory, built_wheel: Path
) -> Path:
    """A session-wide venv with the locally-built wheel installed.

    Returns the venv's python executable. Shared across every e2e test
    that pins to the *current* wheel. Cross-version tests (which install
    a released PyPI version) must create their own venv.
    """
    root = tmp_path_factory.mktemp("e2e_venv")
    py = make_venv(root)
    pip_install(py, str(built_wheel))
    return py


def make_venv(root: Path) -> Path:
    """Create an isolated venv at *root* and return its python executable."""
    venv.create(root, with_pip=True, clear=True, symlinks=(os.name != "nt"))
    if os.name == "nt":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def pip_install(py_exe: Path, *args: str) -> None:
    """Run ``<py_exe> -m pip install --quiet <args>`` with a non-interactive env.

    ``--no-compile`` skips bytecode compilation during install (saves a few
    seconds per install without affecting test correctness — Python will
    compile modules lazily on first import anyway).
    """
    run_utf8(
        [
            str(py_exe), "-m", "pip", "install",
            "--quiet", "--disable-pip-version-check", "--no-compile",
            *args,
        ],
        check=True,
        timeout=300,
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
    return run_utf8(
        [str(py_exe), "-m", "cataforge", *args],
        cwd=cwd,
        check=check,
    )
