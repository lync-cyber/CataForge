"""event_logger.py — back-compat shim forwarding to ``cataforge event log``.

The canonical invocation in CataForge protocols is::

    cataforge event log --event phase_start --phase architecture --detail "..."

which works from any subdirectory inside a CataForge project (the CLI walks
up to find ``.cataforge/``). Earlier scaffold revisions invoked this file
directly as ``python .cataforge/scripts/framework/event_logger.py …``; that
form breaks under monorepo subdirectory cwds (the relative path can't be
resolved). Protocols were migrated to the CLI form in v0.1.14.

This file is kept as a stable entry point so any external integrations or
hand-written scripts that still call the legacy path continue to work — its
argv passes straight through to ``cataforge event log``.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from cataforge.cli.main import cli
    except ImportError as e:
        sys.stderr.write(
            "event_logger.py: cannot import cataforge "
            f"({e.__class__.__name__}: {e}). Run "
            "`python .cataforge/scripts/framework/setup.py` to install "
            "dependencies, or `pip install cataforge`.\n"
        )
        return 1

    # Click exits on its own via SystemExit — cede control and re-raise.
    cli(args=["event", "log", *sys.argv[1:]], prog_name="event_logger.py")
    return 0  # unreachable; cli() always calls sys.exit


if __name__ == "__main__":
    sys.exit(main())
