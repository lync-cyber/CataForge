"""``cataforge.core.event_log`` frozensets must match
``.cataforge/schemas/event-log.schema.json`` and its scaffold mirror."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.core.event_log import (
    REQUIRED_FIELDS,
    VALID_EVENTS,
    VALID_STATUSES,
    VALID_TASK_TYPES,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATHS = [
    REPO_ROOT / ".cataforge" / "schemas" / "event-log.schema.json",
    REPO_ROOT
    / "src"
    / "cataforge"
    / "_assets"
    / "cataforge_scaffold"
    / "schemas"
    / "event-log.schema.json",
]


def _load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS, ids=lambda p: p.parent.parent.name)
def test_event_enum_matches_python(schema_path: Path) -> None:
    schema = _load_schema(schema_path)
    json_events = set(schema["properties"]["event"]["enum"])
    assert json_events == set(VALID_EVENTS), (
        f"event enum drift in {schema_path.relative_to(REPO_ROOT)}: "
        f"only-in-json={json_events - set(VALID_EVENTS)}, "
        f"only-in-python={set(VALID_EVENTS) - json_events}"
    )


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS, ids=lambda p: p.parent.parent.name)
def test_status_enum_matches_python(schema_path: Path) -> None:
    schema = _load_schema(schema_path)
    json_statuses = set(schema["properties"]["status"]["enum"])
    assert json_statuses == set(VALID_STATUSES), (
        f"status enum drift in {schema_path.relative_to(REPO_ROOT)}: "
        f"only-in-json={json_statuses - set(VALID_STATUSES)}, "
        f"only-in-python={set(VALID_STATUSES) - json_statuses}"
    )


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS, ids=lambda p: p.parent.parent.name)
def test_task_type_enum_matches_python(schema_path: Path) -> None:
    schema = _load_schema(schema_path)
    json_task_types = set(schema["properties"]["task_type"]["enum"])
    assert json_task_types == set(VALID_TASK_TYPES), (
        f"task_type enum drift in {schema_path.relative_to(REPO_ROOT)}: "
        f"only-in-json={json_task_types - set(VALID_TASK_TYPES)}, "
        f"only-in-python={set(VALID_TASK_TYPES) - json_task_types}"
    )


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS, ids=lambda p: p.parent.parent.name)
def test_required_fields_match_python(schema_path: Path) -> None:
    schema = _load_schema(schema_path)
    json_required = tuple(schema["required"])
    assert set(json_required) == set(REQUIRED_FIELDS), (
        f"required-fields drift in {schema_path.relative_to(REPO_ROOT)}: "
        f"only-in-json={set(json_required) - set(REQUIRED_FIELDS)}, "
        f"only-in-python={set(REQUIRED_FIELDS) - set(json_required)}"
    )


def test_two_schema_copies_are_identical() -> None:
    """Scaffold mirror must equal the repo-root copy."""
    a, b = SCHEMA_PATHS
    assert _load_schema(a) == _load_schema(b), (
        f"{a.relative_to(REPO_ROOT)} and "
        f"{b.relative_to(REPO_ROOT)} have diverged — sync them."
    )
