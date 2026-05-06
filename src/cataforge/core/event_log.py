"""Event log writer — persists framework events to ``docs/EVENT-LOG.jsonl``.

Separation of concerns:

* :mod:`cataforge.core.events` is an in-process pub/sub bus used by Python
  call sites (setup/deploy/etc.). Its event names are ``framework:*`` style
  and it carries an arbitrary ``data`` payload.
* This module persists the project-level, cross-session timeline used by
  Orchestrator protocols and TDD/doc-gen Skills — records conform to
  ``.cataforge/schemas/event-log.schema.json`` and are driven by markdown
  protocols shelling out to ``cataforge event log`` (or the legacy
  ``event_logger.py`` shim).

The two should stay decoupled: mixing them causes schema drift. If a
Python call site needs to contribute to the durable log it should call
:func:`append_event` directly, not go through the pub/sub bus.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Mirrors `.cataforge/schemas/event-log.schema.json` — kept in Python so the
# CLI can validate without a hard dependency on the jsonschema package.
VALID_EVENTS: frozenset[str] = frozenset({
    "session_start",
    "session_end",
    "phase_start",
    "phase_end",
    "agent_dispatch",
    "agent_return",
    "review_verdict",
    "user_decision",
    "revision_start",
    "tdd_phase",
    "incident",
    "state_change",
    "correction",
    "doc_finalize",
})

VALID_STATUSES: frozenset[str] = frozenset({
    "completed",
    "needs_input",
    "blocked",
    "approved",
    "approved_with_notes",
    "needs_revision",
    "rolled-back",
})

VALID_TASK_TYPES: frozenset[str] = frozenset({
    "new_creation",
    "revision",
    "continuation",
    "retrospective",
    "skill-improvement",
    "apply-learnings",
    "amendment",
})

REQUIRED_FIELDS: tuple[str, ...] = ("ts", "event", "phase", "detail")
ALLOWED_FIELDS: frozenset[str] = frozenset({
    "ts", "event", "phase", "agent", "task_type", "status", "ref", "detail",
})

# Relative to project root.
EVENT_LOG_REL = Path("docs") / "EVENT-LOG.jsonl"


class EventLogError(ValueError):
    """Raised when a record fails schema validation or the log is unwritable."""


def now_iso() -> str:
    """UTC timestamp with second precision, matching schema ``date-time``."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_record(record: Mapping[str, Any]) -> list[str]:
    """Return a list of human-readable validation errors (empty if OK)."""
    errors: list[str] = []

    unknown = set(record) - ALLOWED_FIELDS
    if unknown:
        errors.append(f"unknown field(s): {sorted(unknown)}")

    for field in REQUIRED_FIELDS:
        if field not in record or record[field] in (None, ""):
            errors.append(f"missing required field: {field!r}")

    event = record.get("event")
    if event is not None and event not in VALID_EVENTS:
        errors.append(
            f"event={event!r} not in enum "
            f"(known: {sorted(VALID_EVENTS)})"
        )

    status = record.get("status")
    if status is not None and status not in VALID_STATUSES:
        errors.append(
            f"status={status!r} not in enum "
            f"(known: {sorted(VALID_STATUSES)})"
        )

    task_type = record.get("task_type")
    if task_type is not None and task_type not in VALID_TASK_TYPES:
        errors.append(
            f"task_type={task_type!r} not in enum "
            f"(known: {sorted(VALID_TASK_TYPES)})"
        )

    for field in ("ts", "event", "phase", "detail", "agent", "status",
                  "ref", "task_type"):
        val = record.get(field)
        if val is None:
            continue
        if not isinstance(val, str):
            errors.append(f"field {field!r} must be a string, got {type(val).__name__}")
            continue
        try:
            val.encode("utf-8")
        except UnicodeEncodeError:
            errors.append(
                f"field {field!r} contains invalid surrogate code points "
                f"(likely mis-decoded input — ensure source is UTF-8)"
            )

    return errors


def build_record(
    *,
    event: str,
    phase: str,
    detail: str,
    agent: str | None = None,
    status: str | None = None,
    ref: str | None = None,
    task_type: str | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    """Assemble a record dict, filling ``ts`` if absent. Validates before return."""
    record: dict[str, Any] = {
        "ts": ts or now_iso(),
        "event": event,
        "phase": phase,
        "detail": detail,
    }
    if agent is not None:
        record["agent"] = agent
    if status is not None:
        record["status"] = status
    if ref is not None:
        record["ref"] = ref
    if task_type is not None:
        record["task_type"] = task_type

    errors = validate_record(record)
    if errors:
        raise EventLogError("; ".join(errors))
    return record


def event_log_path(project_root: Path) -> Path:
    """Path to ``docs/EVENT-LOG.jsonl`` under *project_root*."""
    return project_root / EVENT_LOG_REL


def append_event(project_root: Path, record: Mapping[str, Any]) -> Path:
    """Validate and append a single record; returns the log file path.

    Missing parent directories are created (the ``docs/`` folder in fresh
    projects won't exist until a doc is generated). Writes are line-buffered
    to keep recovery simple: a partial write leaves at most one truncated
    line, which the reader can discard.
    """
    errors = validate_record(record)
    if errors:
        raise EventLogError("; ".join(errors))

    path = event_log_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(record, ensure_ascii=False, sort_keys=False)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")
    return path


def append_batch(
    project_root: Path,
    records: Iterable[Mapping[str, Any]],
) -> tuple[Path, int]:
    """Atomic batch append: validate every record first, then write them all.

    Either every record lands in the log or none does — the batch is written
    to a sibling temp file and ``os.replace``'d only after validation passes.
    On POSIX this is atomic within a filesystem; on Windows ``os.replace``
    is likewise atomic when source and dest are on the same volume (which
    they are here — both live under *project_root*).

    Returns ``(log_path, count)``.
    """
    records = list(records)
    if not records:
        raise EventLogError("batch is empty")

    for i, rec in enumerate(records):
        errors = validate_record(rec)
        if errors:
            raise EventLogError(f"record #{i}: {'; '.join(errors)}")

    path = event_log_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = path.read_bytes() if path.is_file() else b""
    new_lines = "".join(
        json.dumps(rec, ensure_ascii=False, sort_keys=False) + "\n"
        for rec in records
    ).encode("utf-8")

    # Same directory so os.replace is atomic on every supported OS.
    fd, tmp_name = tempfile.mkstemp(
        prefix=".event-log-", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "wb") as f:
            if existing and not existing.endswith(b"\n"):
                # Heal a previously truncated line so the replace leaves a
                # clean JSONL stream.
                f.write(existing + b"\n")
            else:
                f.write(existing)
            f.write(new_lines)
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise

    return path, len(records)


def parse_batch_stream(text: str) -> list[dict[str, Any]]:
    """Parse a JSON-Lines string into record dicts. Used by the CLI ``--batch``.

    Blank lines are skipped. Non-object lines, unparseable lines, and records
    missing ``ts`` are all handled here — ``ts`` is filled in automatically so
    callers writing by hand don't need to produce ISO timestamps.
    """
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise EventLogError(f"line {i}: invalid JSON: {e}") from None
        if not isinstance(obj, dict):
            raise EventLogError(
                f"line {i}: expected JSON object, got {type(obj).__name__}"
            )
        obj.setdefault("ts", now_iso())
        out.append(obj)
    return out
