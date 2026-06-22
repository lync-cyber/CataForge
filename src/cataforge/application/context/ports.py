"""Capability ports + per-operation fidelity declarations.

A *capability port* is a backend-agnostic contract for one slice of the
context-IO lifecycle. A backend declares, per operation, how faithfully
it can serve that operation:

* ``NATIVE``      — first-class implementation (no information loss).
* ``DEGRADED``    — can serve, but with known loss (e.g. static index
  dependency fields vs a graph closure).
* ``UNSUPPORTED`` — structurally cannot serve; the router skips it.

The router orders the mode's enabled backends by their declared
fidelity for the requested operation and consults them highest-first.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Protocol, runtime_checkable


class Fidelity(IntEnum):
    """How faithfully a backend can serve an operation (higher = better)."""

    UNSUPPORTED = 0
    DEGRADED = 1
    NATIVE = 2


@runtime_checkable
class ContextBackend(Protocol):
    """Common backend surface the router introspects."""

    name: str
    fidelity: dict[str, Fidelity]


@runtime_checkable
class ContextReadPort(Protocol):
    """Read a section's content; ``None`` means 'this backend cannot serve'."""

    def read_section(
        self, ref: str, project_root: str, *, file_cache: dict[str, list[str]] | None = None
    ) -> str | None: ...

    def plan_load(
        self, refs: list[str], project_root: str, token_budget: int
    ) -> tuple[list[str], list[str]] | None: ...


@runtime_checkable
class RelationPort(Protocol):
    """Relation/traceability queries over context content."""

    def deps(self, ref: str, project_root: str, max_depth: int) -> list[str] | None: ...


# Operation identifiers used as keys in a backend's ``fidelity`` map.
OP_READ_SECTION = "read_section"
OP_PLAN_LOAD = "plan_load"
OP_DEPS = "deps"
