"""``cataforge correction`` — write On-Correction Learning entries.

Used by the orchestrator for the interrupt-override trigger path
(option-override and review-flag are hook-driven).
"""

from __future__ import annotations

import click

from cataforge.cli.main import cli
from cataforge.core.corrections import (
    VALID_DEVIATIONS,
    VALID_TRIGGERS,
    record_correction,
)
from cataforge.core.paths import find_project_root


@cli.group("correction")
def correction_group() -> None:
    """Record and inspect On-Correction Learning entries."""


@correction_group.command("record")
@click.option(
    "--trigger",
    type=click.Choice(sorted(VALID_TRIGGERS)),
    required=True,
    help="Trigger signal (option-override / interrupt-override / review-flag).",
)
@click.option("--agent", required=True, help="Originating agent id.")
@click.option(
    "--phase",
    required=True,
    help="Protocol phase (e.g. architecture, implementation, review).",
)
@click.option(
    "--question",
    required=True,
    help="Question or assumption text being corrected.",
)
@click.option(
    "--baseline",
    required=True,
    help="Recommended option / upstream baseline value.",
)
@click.option("--actual", required=True, help="User-chosen / actual value.")
@click.option(
    "--deviation",
    type=click.Choice(sorted(VALID_DEVIATIONS)),
    default="self-caused",
    show_default=True,
    help="Deviation category (counts toward RETRO_TRIGGER_SELF_CAUSED "
    "threshold when self-caused).",
)
@click.option(
    "--no-event-log",
    is_flag=True,
    default=False,
    help="Skip the EVENT-LOG dual-write (CORRECTIONS-LOG only).",
)
def record_command(
    trigger: str,
    agent: str,
    phase: str,
    question: str,
    baseline: str,
    actual: str,
    deviation: str,
    no_event_log: bool,
) -> None:
    """Append a correction record to CORRECTIONS-LOG.md and EVENT-LOG.jsonl."""
    project_root = find_project_root()
    result = record_correction(
        project_root,
        trigger=trigger,
        agent=agent,
        phase=phase,
        question=question,
        baseline=baseline,
        actual=actual,
        deviation=deviation,
        write_event_log=not no_event_log,
    )
    click.echo(f"CORRECTIONS-LOG: {result['corrections_log']}")
    if result["event_log"] is not None:
        click.echo(f"EVENT-LOG:       {result['event_log']}")
    elif not no_event_log:
        click.echo(
            "EVENT-LOG: (write failed — see log / rerun with "
            "CATAFORGE_HOOK_DEBUG=1)"
        )
