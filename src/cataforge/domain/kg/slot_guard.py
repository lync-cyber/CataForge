"""Write-time slot-value validation for the authoring doors.

Enum-ranged slots (``task_status``, ``status``, ``test_result``, …) are plain
string literals in the store, so a typo or a value written to the wrong slot
(`status=done` instead of `task_status=done`) corrupts silently: SPARQL
filters stop matching and every downstream checker sees "unset". This module
closes that hole at the transaction layer:

* enum membership — the value of an enum-ranged slot must be a member of the
  LinkML-declared enum. The enum universe is introspected from the generated
  Pydantic module (single source: ``schemas/core.yaml`` via codegen), so no
  hand-maintained value tables can drift.
* ``task_status`` lifecycle — updates must follow the task state machine
  below. An out-of-band jump (``done → in_progress`` rework, imported
  history, manual repair) needs an explicit acknowledgement flag, mirroring
  the ``--ack-*`` decision pattern of `cataforge phase transition`.

Creation is exempt from the transition rule (any enum member is a legal
initial state — bulk ingest and authoring set states from documents), and
stores whose codegen module is absent degrade to no-op so minimal installs
keep writing.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import get_args

from cataforge.domain.kg._errors import KGValidationError

# Legal task_status transitions. `done` / `cancelled` are terminal: leaving
# them is rework and requires ack_status_jump so a silent regression cannot
# masquerade as progress.
TASK_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "todo": frozenset({"in_progress", "blocked", "cancelled"}),
    "in_progress": frozenset({"review", "done", "blocked", "todo", "cancelled"}),
    "review": frozenset({"done", "in_progress", "blocked", "cancelled"}),
    "blocked": frozenset({"todo", "in_progress", "cancelled"}),
    "done": frozenset(),
    "cancelled": frozenset(),
}


@lru_cache(maxsize=1)
def _generated_module() -> object | None:
    try:
        from cataforge.domain.kg._generated import core_pydantic  # noqa: PLC0415
    except Exception:  # pragma: no cover — codegen module absent/broken
        return None
    return core_pydantic


def _enum_from_annotation(annotation: object) -> type[Enum] | None:
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation
    for arg in get_args(annotation):
        found = _enum_from_annotation(arg)
        if found is not None:
            return found
    return None


@lru_cache(maxsize=256)
def enum_values_for(class_name: str, slot: str) -> frozenset[str] | None:
    """Permissible values of ``slot`` on ``class_name``; None when unconstrained.

    Unknown classes/slots and non-enum slots return None (no constraint) —
    the guard only rejects what the schema demonstrably forbids.
    """
    module = _generated_module()
    if module is None:
        return None
    model = getattr(module, class_name, None)
    fields = getattr(model, "model_fields", None)
    if not fields or slot not in fields:
        return None
    enum_cls = _enum_from_annotation(fields[slot].annotation)
    if enum_cls is None:
        return None
    return frozenset(member.value for member in enum_cls)


def check_enum_value(class_name: str, slot: str, value: str) -> None:
    """Raise ``KGValidationError`` when ``value`` violates the slot's enum range."""
    allowed = enum_values_for(class_name, slot)
    if allowed is not None and value not in allowed:
        raise KGValidationError(
            f"{class_name}.{slot} rejects {value!r}; allowed values: {', '.join(sorted(allowed))}"
        )


def check_task_status_transition(
    current: str | None, new: str, *, ack_status_jump: bool = False
) -> None:
    """Raise ``KGValidationError`` on an illegal ``task_status`` move.

    ``current is None`` (slot unset) and ``current == new`` are always legal.
    ``ack_status_jump`` permits any enum-legal jump — the caller owns making
    that decision auditable.
    """
    if current is None or current == new or ack_status_jump:
        return
    allowed = TASK_STATUS_TRANSITIONS.get(current)
    if allowed is None:
        # Stored value predates the guard or came from a foreign tool; any
        # enum-legal value may repair it.
        return
    if new not in allowed:
        legal = ", ".join(sorted(allowed)) or "(terminal state)"
        raise KGValidationError(
            f"illegal task_status transition {current!r} → {new!r}; legal next "
            f"states: {legal}. Pass --ack-status-jump to override deliberately "
            "(rework / manual repair)."
        )
