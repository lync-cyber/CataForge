"""Write-time slot validation: enum ranges + the task_status state machine."""

from __future__ import annotations

import pytest

from cataforge.domain.kg._errors import KGValidationError
from cataforge.domain.kg.slot_guard import (
    TASK_STATUS_TRANSITIONS,
    check_enum_value,
    check_task_status_transition,
    enum_values_for,
)

# ---- enum introspection (generated pydantic is the single source) -----------


def test_enum_values_introspected_from_schema() -> None:
    assert enum_values_for("Task", "task_status") == frozenset(
        {"todo", "in_progress", "blocked", "review", "done", "cancelled"}
    )


def test_artifact_status_enum_has_no_done_member() -> None:
    # The historical `--slot status=done` drift: `status` is the artifact
    # lifecycle enum, which must NOT accept task execution states.
    values = enum_values_for("Task", "status")
    assert values is not None
    assert "done" not in values
    assert "approved" in values


def test_non_enum_slot_is_unconstrained() -> None:
    assert enum_values_for("Feature", "title") is None


def test_unknown_class_and_slot_are_unconstrained() -> None:
    assert enum_values_for("NoSuchClass", "task_status") is None
    assert enum_values_for("Task", "no_such_slot") is None


def test_check_enum_value_accepts_member_and_rejects_stranger() -> None:
    check_enum_value("Task", "task_status", "done")
    with pytest.raises(KGValidationError, match="allowed values"):
        check_enum_value("Task", "task_status", "finished")


def test_check_enum_value_rejects_wrong_slot_vocabulary() -> None:
    with pytest.raises(KGValidationError, match="Task.status rejects 'done'"):
        check_enum_value("Task", "status", "done")


# ---- task_status transition table -------------------------------------------


def test_transition_table_covers_every_enum_member() -> None:
    assert frozenset(TASK_STATUS_TRANSITIONS) == enum_values_for("Task", "task_status")


@pytest.mark.parametrize(
    ("current", "new"),
    [
        ("todo", "in_progress"),
        ("in_progress", "review"),
        ("in_progress", "done"),
        ("review", "done"),
        ("review", "in_progress"),
        ("in_progress", "blocked"),
        ("blocked", "in_progress"),
        ("todo", "cancelled"),
    ],
)
def test_legal_transitions_pass(current: str, new: str) -> None:
    check_task_status_transition(current, new)


@pytest.mark.parametrize(
    ("current", "new"),
    [
        ("todo", "done"),
        ("todo", "review"),
        ("done", "in_progress"),
        ("cancelled", "todo"),
        ("blocked", "done"),
    ],
)
def test_illegal_transitions_rejected(current: str, new: str) -> None:
    with pytest.raises(KGValidationError, match="illegal task_status transition"):
        check_task_status_transition(current, new)


def test_ack_status_jump_overrides() -> None:
    check_task_status_transition("done", "in_progress", ack_status_jump=True)


def test_unset_current_and_noop_are_legal() -> None:
    check_task_status_transition(None, "done")
    check_task_status_transition("done", "done")


def test_foreign_stored_value_is_repairable() -> None:
    # A pre-guard store may carry junk; any move away from it is a repair.
    check_task_status_transition("wip", "in_progress")
