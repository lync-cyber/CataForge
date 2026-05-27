"""Unified subprocess invocation wrapper.

Most ``subprocess.run`` call sites in this repo had to re-decide the
same handful of policies every time: timeout, ``check=True`` vs
``check=False`` plus manual returncode handling, ``capture_output=True``
vs explicit ``stdout=PIPE``, text mode + encoding for Windows safety.
Different decisions in different files meant a Codex shell-out and a
git probe handled errors in subtly different ways even when both
"just wanted to capture stdout."

This helper centralises the policy:

* ``check=False`` always — the caller decides what a non-zero return
  means. Sets aside the ``CalledProcessError`` path in favour of
  explicit ``CompletedProcess.returncode`` inspection downstream.
* Default ``timeout=DEFAULT_TIMEOUT_SECONDS`` (60s) so a hung helper
  can't block the CLI forever. Pass ``timeout=None`` for genuinely
  unbounded operations (e.g. ``cataforge sync-main`` waiting on git
  fetch over a slow link).
* ``text=True`` + ``encoding="utf-8"`` by default so the Windows
  ``cp1252`` fallback path doesn't garble output.
* ``capture_output=True`` by default — most callers want stdout/stderr
  in the returned ``CompletedProcess``. Pass ``capture_output=False``
  to stream straight to the terminal.

Migrating call sites is gradual (see
``scripts/checks/check_no_raw_subprocess.py`` for the advisory tally).
A migration pattern is in the docstring of :func:`run`.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 60.0


def run(
    argv: Sequence[str],
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = DEFAULT_TIMEOUT_SECONDS,
    capture_output: bool = True,
    input: str | None = None,
    encoding: str = "utf-8",
) -> subprocess.CompletedProcess[str]:
    """Run *argv* with the repo-wide subprocess policy.

    Never raises ``CalledProcessError`` — inspect ``.returncode`` on
    the returned ``CompletedProcess``. ``subprocess.TimeoutExpired``
    and ``FileNotFoundError`` (binary not on PATH) still propagate so
    the caller can decide between "diagnose and continue" vs
    "raise CataforgeError to abort the command".

    Migration pattern from a raw ``subprocess.run``:

    Before::

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo, text=True, capture_output=True,
            check=True, encoding="utf-8",
        )
        sha = result.stdout.strip()

    After::

        from cataforge.utils.run_subprocess import run as run_proc
        result = run_proc(["git", "rev-parse", "HEAD"], cwd=repo)
        if result.returncode != 0:
            raise ExternalToolError(
                f"git rev-parse failed: {result.stderr or result.stdout}"
            )
        sha = result.stdout.strip()

    The migration is gradual: existing raw call sites continue to work
    and there is no enforcement guard (yet) — see
    ``scripts/checks/check_no_raw_subprocess.py`` for an advisory
    inventory.
    """
    return subprocess.run(  # noqa: S603  intentional — this is the centralised wrapper
        list(argv),
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        timeout=timeout,
        capture_output=capture_output,
        input=input,
        text=True,
        encoding=encoding,
        check=False,
    )


__all__ = ["DEFAULT_TIMEOUT_SECONDS", "run"]
