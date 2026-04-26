#!/usr/bin/env python3
"""Anti-rot guard: `.cataforge/schemas/*.schema.json` and their Python mirrors stay in sync.

The two formal JSON Schema files (`event-log.schema.json`,
`agent-result.schema.json`) live as documentation only — neither is
consumed by a `jsonschema.validate` call at runtime (no `jsonschema`
dep). Validation is hand-rolled in:

  - `cataforge.core.event_log`   (validate_record / VALID_EVENTS / VALID_STATUSES /
                                  VALID_TASK_TYPES / REQUIRED_FIELDS / ALLOWED_FIELDS)
  - `cataforge.hook.scripts.validate_agent_result`
                                  (VALID_STATUSES fallback constant — primary path
                                   reads the schema file at runtime)

When someone edits the JSON file but forgets the Python mirror (or vice
versa), validation diverges silently — events the schema rejects could
be accepted by the writer, or the writer rejects events the schema
allows. This guard fails fast in CI and pre-commit.

Fails (exit 1) on any of:
  - event-log enum drift (event / status / task_type)
  - event-log required-fields drift
  - event-log allowed-fields drift (schema properties keys vs ALLOWED_FIELDS)
  - agent-result status enum drift (schema vs hook fallback constant)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / ".cataforge" / "schemas"

# Make src/ importable so we don't rely on the package being installed.
sys.path.insert(0, str(REPO_ROOT / "src"))

from cataforge.core import event_log  # noqa: E402
from cataforge.hook.scripts import validate_agent_result  # noqa: E402


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_event_log() -> list[str]:
    schema = _load(SCHEMA_DIR / "event-log.schema.json")
    props = schema["properties"]
    errs: list[str] = []

    expected_events = set(props["event"]["enum"])
    if expected_events != event_log.VALID_EVENTS:
        only_schema = sorted(expected_events - event_log.VALID_EVENTS)
        only_python = sorted(event_log.VALID_EVENTS - expected_events)
        errs.append(
            "event-log: VALID_EVENTS drift\n"
            f"  only in schema: {only_schema}\n"
            f"  only in Python: {only_python}"
        )

    expected_statuses = set(props["status"]["enum"])
    if expected_statuses != event_log.VALID_STATUSES:
        errs.append(
            "event-log: VALID_STATUSES drift\n"
            f"  only in schema: {sorted(expected_statuses - event_log.VALID_STATUSES)}\n"
            f"  only in Python: {sorted(event_log.VALID_STATUSES - expected_statuses)}"
        )

    expected_task_types = set(props["task_type"]["enum"])
    if expected_task_types != event_log.VALID_TASK_TYPES:
        errs.append(
            "event-log: VALID_TASK_TYPES drift\n"
            f"  only in schema: {sorted(expected_task_types - event_log.VALID_TASK_TYPES)}\n"
            f"  only in Python: {sorted(event_log.VALID_TASK_TYPES - expected_task_types)}"
        )

    expected_required = tuple(schema["required"])
    if expected_required != event_log.REQUIRED_FIELDS:
        errs.append(
            "event-log: REQUIRED_FIELDS drift\n"
            f"  schema: {expected_required}\n"
            f"  Python: {event_log.REQUIRED_FIELDS}"
        )

    expected_allowed = set(props.keys())
    if expected_allowed != event_log.ALLOWED_FIELDS:
        errs.append(
            "event-log: ALLOWED_FIELDS drift\n"
            f"  only in schema: {sorted(expected_allowed - event_log.ALLOWED_FIELDS)}\n"
            f"  only in Python: {sorted(event_log.ALLOWED_FIELDS - expected_allowed)}"
        )

    return errs


def _check_agent_result() -> list[str]:
    schema = _load(SCHEMA_DIR / "agent-result.schema.json")
    expected = set(schema["properties"]["status"]["enum"])
    fallback = validate_agent_result.VALID_STATUSES
    if expected != fallback:
        return [
            "agent-result: VALID_STATUSES fallback drift\n"
            f"  only in schema: {sorted(expected - fallback)}\n"
            f"  only in Python: {sorted(fallback - expected)}"
        ]
    return []


def main() -> int:
    errs = _check_event_log() + _check_agent_result()
    if errs:
        print("FAIL: schema vs Python mirror parity\n", file=sys.stderr)
        for e in errs:
            print(f"  - {e}\n", file=sys.stderr)
        print(
            "Fix: edit either the .schema.json file or the Python mirror so "
            "both agree, then rerun.",
            file=sys.stderr,
        )
        return 1
    print(
        "OK: schema vs Python mirror parity (event-log: 5 fields/enums; "
        "agent-result: 1 enum)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
