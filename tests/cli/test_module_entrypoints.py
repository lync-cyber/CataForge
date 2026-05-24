"""Both `python -m cataforge` and `python -m cataforge.cli.main` must
invoke the CLI. The former is the canonical entrypoint via __main__.py;
the latter is a defense-in-depth guard against silent no-op subprocess
calls from downstream callers (e.g., hook scripts)."""

from __future__ import annotations

import subprocess
import sys


def _run(module: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module, "--help"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def test_python_m_cataforge_runs_cli() -> None:
    result = _run("cataforge")
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "Usage:" in combined and "bootstrap" in combined, (
        f"expected click --help with 'Usage:' + 'bootstrap'; got: {combined[:200]!r}"
    )


def test_python_m_cataforge_cli_main_runs_cli() -> None:
    result = _run("cataforge.cli.main")
    assert result.returncode == 0, (
        "python -m cataforge.cli.main must invoke the CLI; an empty "
        "stdout with returncode 0 indicates the __main__ block is missing"
    )
    combined = result.stdout + result.stderr
    assert "Usage:" in combined and "bootstrap" in combined, (
        f"expected click --help with 'Usage:' + 'bootstrap'; got: {combined[:200]!r}"
    )
