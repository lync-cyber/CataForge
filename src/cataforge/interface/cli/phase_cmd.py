"""cataforge phase — read-only inspection of a project's workflow phase.

Distinguishes "framework deployed" from "workflow actually driven": a fresh
deploy leaves the instruction file's 当前阶段 as a placeholder with no docs,
no EVENT-LOG, no index. ``phase status`` checks the current phase's expected
artifacts exist and exits non-zero when they don't, giving orchestration a
machine-checkable phase boundary. The evaluation logic lives in
:mod:`cataforge.application.phase`; this module is the thin CLI surface.
"""

from __future__ import annotations

import click

from cataforge.application.phase import evaluate_phase
from cataforge.core.errors import CataforgeError
from cataforge.interface.cli.helpers import resolve_root
from cataforge.interface.cli.main import cli


@cli.group("phase")
def phase_group() -> None:
    """Read-only inspection of a project's SDLC workflow phase."""


@phase_group.command("status")
def phase_status() -> None:
    """Verify the current phase's expected artifacts exist.

    Exit 0 when every check for the current phase passes; exit 1 when an
    expected artifact is missing (phase not driven, doc absent/unindexed, no
    phase_start); exit 2 when the project has no instruction file.
    """
    root = resolve_root()
    current, checks = evaluate_phase(root)

    click.echo(f"Phase: {current}")
    for label, ok, detail in checks:
        mark = "OK  " if ok else "FAIL"
        click.echo(f"  [{mark}] {label}: {detail}")

    failed = [label for label, ok, _ in checks if not ok]
    if failed:
        err = CataforgeError(
            f"phase {current!r}: {len(failed)} expected artifact(s) missing — " + ", ".join(failed)
        )
        err.exit_code = 1
        raise err
    click.echo(f"OK: phase {current!r} artifacts present")
