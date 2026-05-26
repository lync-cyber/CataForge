"""Resolve a Python interpreter with cataforge importable, then exec the CLI.

Pre-commit hooks that invoke ``cataforge`` need an interpreter that has the
package installed, but no single mechanism works for every contributor:

* uv users want ``uv run --extra dev python -m ...`` so the call resolves to
  the project's managed ``.venv``.
* pip-venv users want their currently-activated venv's interpreter (passed
  through ``$VIRTUAL_ENV``).
* CI runners typically ``pip install -e .`` into the system Python and just
  expect ``python -m cataforge.cli.main`` to work.
* Contributors who have neither uv nor an active venv usually still have a
  ``.venv/`` at the repo root.

Probe in priority order so any of those setups works without explicit
configuration. The wrapper itself imports nothing from cataforge, so it can
always run under whatever Python pre-commit launches it with.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Inline stdio reconfigure — this wrapper deliberately does not import from
# cataforge (chicken-and-egg: we run before cataforge is guaranteed to be
# importable), so ensure_utf8_stdio() is unavailable. Windows cp1252
# default would otherwise crash on any non-ASCII in error messages.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _candidate_venv_pythons(venv_root: Path) -> list[Path]:
    """Return the two standard interpreter paths for a venv (POSIX + Windows)."""
    return [
        venv_root / "bin" / "python",
        venv_root / "bin" / "python3",
        venv_root / "Scripts" / "python.exe",
    ]


def _resolve_interpreter() -> tuple[str, list[str]]:
    """Return ``(executable, prefix_argv)`` of an interpreter that has cataforge.

    ``prefix_argv`` is inserted between the executable and the ``-m
    cataforge.cli.main ...`` portion; it is empty for direct interpreter
    calls and ``["run", "--extra", "dev", "python"]`` for the ``uv``
    fallthrough.
    """
    # 1. Active venv — pre-commit inherits VIRTUAL_ENV from the caller's
    #    shell, so if the contributor has any venv activated we use it.
    active_venv = os.environ.get("VIRTUAL_ENV")
    if active_venv:
        for candidate in _candidate_venv_pythons(Path(active_venv)):
            if candidate.is_file():
                return str(candidate), []

    # 2. Project-local .venv — the convention every CataForge contributor
    #    doc points at; works even if the contributor forgot to activate.
    for candidate in _candidate_venv_pythons(_REPO_ROOT / ".venv"):
        if candidate.is_file():
            return str(candidate), []

    # 3. uv on PATH — keeps the original commit's behavior for uv users
    #    without making it a hard requirement.
    uv = shutil.which("uv")
    if uv:
        return uv, ["run", "--extra", "dev", "python"]

    # 4. Whatever Python is running this wrapper — last resort for CI
    #    runners that pip-installed cataforge into the system interpreter.
    return sys.executable, []


def main() -> int:
    interp, prefix = _resolve_interpreter()
    cmd = [interp, *prefix, "-m", "cataforge.cli.main", *sys.argv[1:]]
    try:
        return subprocess.call(cmd)
    except FileNotFoundError as exc:
        # Surface the resolved path so the contributor knows which probe won.
        print(
            f"run_cataforge: resolved interpreter {interp!r} not executable: {exc}",
            file=sys.stderr,
        )
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
