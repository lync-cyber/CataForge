"""cataforge event — persistent project event log (``docs/EVENT-LOG.jsonl``).

The backing writer lives in :mod:`cataforge.core.event_log`. This module is
just the Click surface + a small amount of argv juggling for the legacy
``event_logger.py`` shim that markdown protocols still invoke.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from cataforge.cli.errors import CataforgeError
from cataforge.cli.main import cli
from cataforge.core.event_log import (
    EventLogError,
    append_batch,
    append_event,
    build_record,
    parse_batch_stream,
)
from cataforge.core.paths import find_project_root


@cli.group("event")
def event_group() -> None:
    """Project event log (``docs/EVENT-LOG.jsonl``).

    Append schema-validated records driven by Orchestrator/TDD/doc-gen
    protocols. See ``.cataforge/schemas/event-log.schema.json`` for the
    record format.
    """


@event_group.command("log")
@click.option(
    "--event",
    "event_name",
    type=str,
    default=None,
    help="Event type (schema enum, e.g. phase_start, agent_dispatch).",
)
@click.option("--phase", type=str, default=None, help="Current project phase.")
@click.option("--agent", type=str, default=None, help="Agent directory name (optional).")
@click.option(
    "--status", type=str, default=None,
    help="Result status (optional, schema enum).",
)
@click.option(
    "--task-type", type=str, default=None,
    help="agent-dispatch task type (optional, schema enum).",
)
@click.option("--ref", type=str, default=None, help="doc_id#section or file path.")
@click.option("--detail", type=str, default=None, help="Short description.")
@click.option(
    "--data",
    type=str,
    default=None,
    help="JSON object merged into the record (fields override CLI flags on conflict).",
)
@click.option(
    "--batch",
    is_flag=True,
    help="Read JSON-Lines records from stdin and append atomically.",
)
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Override project root (default: walk up for .cataforge/).",
)
def event_log_cmd(
    event_name: str | None,
    phase: str | None,
    agent: str | None,
    status: str | None,
    task_type: str | None,
    ref: str | None,
    detail: str | None,
    data: str | None,
    batch: bool,
    project_root: Path | None,
) -> None:
    """Append one or more events to ``docs/EVENT-LOG.jsonl``.

    Single-record mode:

        cataforge event log --event phase_start --phase architecture \\
            --detail "进入架构设计阶段"

    Batch mode reads JSON-Lines from stdin; each line is a complete record
    (``ts`` is auto-filled if missing):

        cataforge event log --batch <<'EOF'
        {"event":"phase_end","phase":"dev_planning","status":"approved","detail":"..."}
        {"event":"phase_start","phase":"development","detail":"..."}
        EOF
    """
    root = project_root or find_project_root()

    if batch:
        if event_name or phase or detail or data:
            raise CataforgeError(
                "--batch is mutually exclusive with "
                "--event/--phase/--detail/--data."
            )
        text = sys.stdin.read()
        if not text.strip():
            raise CataforgeError("--batch requested but stdin is empty.")
        try:
            records = parse_batch_stream(text)
            path, count = append_batch(root, records)
        except EventLogError as e:
            raise CataforgeError(f"event batch rejected: {e}") from e
        click.echo(f"Appended {count} event(s) to {path}")
        return

    if not event_name or not phase or not detail:
        raise CataforgeError(
            "--event, --phase, and --detail are all required "
            "(or use --batch for stdin input)."
        )

    extra: dict[str, object] = {}
    if data:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as e:
            raise CataforgeError(f"--data is not valid JSON: {e}") from e
        if not isinstance(parsed, dict):
            raise CataforgeError("--data must be a JSON object.")
        extra = parsed

    try:
        record = build_record(
            event=str(extra.pop("event", event_name)),
            phase=str(extra.pop("phase", phase)),
            detail=str(extra.pop("detail", detail)),
            agent=_opt(extra.pop("agent", agent)),
            status=_opt(extra.pop("status", status)),
            ref=_opt(extra.pop("ref", ref)),
            task_type=_opt(extra.pop("task_type", task_type)),
            ts=_opt(extra.pop("ts", None)),
        )
    except EventLogError as e:
        raise CataforgeError(f"event rejected: {e}") from e

    if extra:
        raise CataforgeError(
            f"--data contains unknown field(s): {sorted(extra)}"
        )

    try:
        path = append_event(root, record)
    except EventLogError as e:
        raise CataforgeError(f"event rejected: {e}") from e
    click.echo(f"Appended event to {path}")


def _opt(value: object) -> str | None:
    """Normalize CLI/data values: blank strings → None, ``None`` passes through."""
    if value is None:
        return None
    s = str(value)
    return s if s != "" else None
