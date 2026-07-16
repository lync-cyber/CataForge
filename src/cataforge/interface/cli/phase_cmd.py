"""cataforge phase — inspect and gate a project's workflow phase.

``phase status`` distinguishes "framework deployed" from "workflow actually
driven": a fresh deploy leaves the instruction file's 当前阶段 as a
placeholder with no docs, no EVENT-LOG, no index; the command checks the
current phase's expected artifacts exist and exits non-zero when they don't.
``phase transition`` runs the Phase Transition Protocol's deterministic gate
chain. The logic lives in :mod:`cataforge.application.phase` /
:mod:`cataforge.application.phase_transition`; this module is the thin CLI
surface.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from cataforge.application.phase import evaluate_phase
from cataforge.core.errors import CataforgeError
from cataforge.interface.cli._support.helpers import resolve_root, root_relative_default
from cataforge.interface.cli.main import cli


@cli.group("phase")
def phase_group() -> None:
    """Inspect the SDLC workflow phase and gate its transitions."""


@phase_group.command("status")
@click.option("--project-root", default=None)
@click.option(
    "--entry",
    is_flag=True,
    default=False,
    help="Phase-entry mode: only verify the phase is recognised and its "
    "phase_start event is logged; the phase's docs are not yet expected.",
)
@click.pass_context
def phase_status(ctx: click.Context, project_root: str | None, entry: bool) -> None:
    """Verify the current phase's expected artifacts exist.

    Exit 0 when every check for the current phase passes; exit 1 when an
    expected artifact is missing (phase not driven, doc absent/unindexed, no
    phase_start); exit 2 when the project has no instruction file. With
    ``--entry`` the doc-artifact checks are skipped — use it right after a
    phase transition, before the phase has produced anything.
    """
    resolved = root_relative_default(ctx, "project_root", project_root)
    root = Path(resolved) if resolved is not None else resolve_root()
    current, checks = evaluate_phase(root, entry=entry)

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


@phase_group.command("transition")
@click.option("--from", "from_phase", required=True, help="Phase being closed out.")
@click.option("--to", "to_phase", required=True, help="Phase being entered (per Mode Routing).")
@click.option(
    "--ack-stale-deps",
    is_flag=True,
    default=False,
    help="Acknowledge stale upstream deps: degrade to WARN and log the decision.",
)
@click.option(
    "--ack-inconsistency",
    is_flag=True,
    default=False,
    help="Degrade a doc-consistency CRITICAL/HIGH verdict to WARN and log the decision.",
)
@click.option(
    "--compact",
    is_flag=True,
    default=False,
    help="On a hygiene breach, run the Learnings Registry compaction before re-checking.",
)
@click.option("--json", "json_output", is_flag=True, default=False, help="Emit the report as JSON.")
@click.option("--project-root", default=None)
@click.pass_context
def phase_transition_cmd(
    ctx: click.Context,
    from_phase: str,
    to_phase: str,
    ack_stale_deps: bool,
    ack_inconsistency: bool,
    compact: bool,
    json_output: bool,
    project_root: str | None,
) -> None:
    """Run the Phase Transition Protocol's deterministic gate chain.

    Gates in order: doc-status consistency, dependency freshness, backend
    reconcile, cross-document consistency, transition event batch,
    instruction-file hygiene. Exits 0 when every gate passes (output ends
    with the next phase's dispatch hint); exits 3 at the first gate that
    needs a decision, printing its structured options; exits 1 when a gate's
    tooling itself fails. Re-running after a decision is safe — the event
    batch is idempotent and every earlier gate is read-only.
    """
    from cataforge.application.phase_transition import run_transition

    resolved = root_relative_default(ctx, "project_root", project_root)
    root = Path(resolved) if resolved is not None else resolve_root()

    report = run_transition(
        root,
        from_phase=from_phase,
        to_phase=to_phase,
        ack_stale_deps=ack_stale_deps,
        ack_inconsistency=ack_inconsistency,
        compact=compact,
    )

    if json_output:
        click.echo(json.dumps(report.to_dict(), ensure_ascii=False))
    else:
        click.echo(f"Phase transition: {report.from_phase} → {report.to_phase}")
        for gate in report.gates:
            click.echo(f"  [{gate.outcome.upper():4}] {gate.gate}: {gate.detail}")
        stopped = report.stopped_at
        if stopped and stopped.options:
            click.echo(f"BRANCH at {stopped.gate} — 选项:")
            for i, option in enumerate(stopped.options, start=1):
                click.echo(f"  ({i}) {option.label}: {option.action}")
        if report.ok:
            dispatch = report.dispatch or {}
            hint = dispatch.get("hint") or (
                f"execution_host={dispatch.get('execution_host', '?')}, "
                f"role={dispatch.get('role', '?')} (mode={dispatch.get('mode', '?')})"
                if dispatch
                else "workflow entry not found — 按 §Mode Routing Protocol 处理"
            )
            click.echo(f"OK: gates complete — dispatch {report.to_phase}: {hint}")

    stopped = report.stopped_at
    if stopped is None:
        return
    err = CataforgeError(f"transition stopped at {stopped.gate}: {stopped.detail}")
    err.exit_code = 3 if stopped.outcome == "stop" else 1
    raise err
