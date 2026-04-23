"""event_logger.py — thin shim over ``cataforge event log`` for markdown callers.

Orchestrator/TDD/doc-gen protocols write commands like::

    python .cataforge/scripts/framework/event_logger.py \\
        --event phase_start --phase architecture --detail "..."

Historically this file was expected to be a full CLI; it is now a forwarder
so the single source of truth is :mod:`cataforge.cli.event_cmd`. Its argv
passes straight through to ``cataforge event log``.

Kept as a path-stable entry point so the markdown protocols don't have to
know whether ``cataforge`` is on ``$PATH``. If the ``cataforge`` package
isn't importable, a clear error points the user at ``setup.py``.
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
