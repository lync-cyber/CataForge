"""Lock-in: schemas/*.schema.json and their Python mirrors agree.

Same constraints as `scripts/checks/check_schema_python_parity.py`,
exercised in-process so the unit suite catches drift even without the
anti-rot CI step (e.g. local pre-commit bypassed via --no-verify).
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / ".cataforge" / "schemas"


def _load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_event_log_python_mirrors_match_schema() -> None:
    from cataforge.core import event_log

    schema = _load("event-log.schema.json")
    props = schema["properties"]

    assert set(props["event"]["enum"]) == event_log.VALID_EVENTS
    assert set(props["status"]["enum"]) == event_log.VALID_STATUSES
    assert set(props["task_type"]["enum"]) == event_log.VALID_TASK_TYPES
    assert tuple(schema["required"]) == event_log.REQUIRED_FIELDS
    assert set(props.keys()) == event_log.ALLOWED_FIELDS


def test_agent_result_hook_fallback_matches_schema() -> None:
    from cataforge.hook.scripts import validate_agent_result

    schema = _load("agent-result.schema.json")
    expected = set(schema["properties"]["status"]["enum"])
    assert expected == validate_agent_result.VALID_STATUSES
