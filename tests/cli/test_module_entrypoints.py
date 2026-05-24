"""`python -m cataforge` is the canonical CLI entrypoint (via __main__.py).

`python -m cataforge.cli.main` is structurally unsound: when loaded as
``__main__``, subcommand modules' ``from cataforge.cli.main import cli``
re-imports under the canonical name and creates a second ``cli`` object;
subcommands register on that second instance while ``__main__.cli()``
runs on the first, silently dropping every subcommand."""

from __future__ import annotations

import subprocess
import sys


def _run(module: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def test_python_m_cataforge_runs_cli() -> None:
    result = _run("cataforge", "--help")
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "Usage:" in combined and "bootstrap" in combined, (
        f"expected click --help with 'Usage:' + 'bootstrap'; got: {combined[:200]!r}"
    )


def test_python_m_cataforge_subcommands_resolve() -> None:
    result = _run("cataforge", "kg", "--help")
    assert result.returncode == 0, (
        "python -m cataforge must route to subcommands; missing kg means "
        "subcommand modules did not register against __main__.py's cli"
    )
    combined = result.stdout + result.stderr
    assert "Knowledge-graph" in combined or "kg" in combined.lower()


def test_python_m_cataforge_cli_main_does_not_invoke_kg() -> None:
    # Two failure modes prove the same point — `python -m cataforge.cli.main`
    # must not be treated as a working entrypoint:
    #   (a) without __main__ block: silent no-op, empty stdout/stderr;
    #   (b) with __main__ block: subcommands lost to dual-import → "No
    #       such command 'kg'" on stderr.
    # Either way, kg help text never appears. Use `python -m cataforge`.
    result = _run("cataforge.cli.main", "kg", "--help")
    combined = result.stdout + result.stderr
    assert "Knowledge-graph" not in combined, (
        "python -m cataforge.cli.main appears to be a working entrypoint "
        "(kg --help rendered). This is a false signal — either a bare "
        "__main__ block was re-added to cli/main.py (which only works for "
        "the top-level cli, not subcommands), or some other regression "
        "made dual-import safe. Re-read cli/main.py end-of-file before "
        "deleting this test."
    )
