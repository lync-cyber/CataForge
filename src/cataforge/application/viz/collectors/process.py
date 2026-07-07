"""Process views: SDLC phase progression + EVENT-LOG timeline.

``phase`` reuses :func:`evaluate_phase` so the graph's blocked/ok styling tracks
``cataforge phase status`` exactly; the phase backbone comes from the project's
execution mode (falling back to standard). ``timeline`` reuses the
fault-tolerant EVENT-LOG reader (malformed lines are skipped, never dropped
silently from valid ones).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cataforge.adapter.platform.registry import read_execution_mode
from cataforge.application.feedback.collectors import collect_recent_events
from cataforge.application.phase import evaluate_phase, is_placeholder
from cataforge.core.errors import CataforgeError
from cataforge.core.phases import PHASES
from cataforge.core.viz.model import Edge, Graph, Node, Status, Timeline, TimelineEvent, View
from cataforge.runtime.skill.builtins.framework_review._framework_data import read_workflow_modes


def is_driven(current: str | None) -> bool:
    """Whether *current* names a real workflow phase (vs an unfilled template
    token or an unrecognised value → the project isn't SDLC-driven)."""
    return not is_placeholder(current) and current in PHASES


def sdlc_applicable(root: Path) -> bool:
    """Whether SDLC-pipeline data (phase gates, core docs, KG traceability)
    applies. False only when the project explicitly declares itself non-driven
    (instruction file present but 没有 workflow phase); a project without an
    instruction file is treated as applicable — it may simply be mid-setup."""
    try:
        current, _ = evaluate_phase(root)
    except CataforgeError:
        return True
    return is_driven(current)


@dataclass(frozen=True)
class GateCheck:
    """One phase-gate check, verbatim from :func:`evaluate_phase`."""

    label: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class PhaseDetail:
    """The dashboard stepper's data contract.

    ``current=None`` ⇒ the project isn't workflow-driven (SDLC N/A);
    ``sequence`` is then empty and ``blocked`` false.
    """

    current: str | None
    sequence: tuple[str, ...]
    checks: tuple[GateCheck, ...]
    blocked: bool


def collect_phase_detail(root: Path) -> PhaseDetail:
    """Phase backbone + gate-check details for the dashboard stepper. Raises
    :class:`CataforgeError` when the project has no instruction file."""
    current, raw_checks = evaluate_phase(root)
    if not is_driven(current) or current is None:
        return PhaseDetail(current=None, sequence=(), checks=(), blocked=False)
    checks = tuple(GateCheck(label, ok, detail) for label, ok, detail in raw_checks)
    sequence = phase_sequence(root)
    if current not in sequence:
        # a recognised phase outside the mode's own backbone (mode switch /
        # hand-edited instruction file) still renders instead of crashing
        sequence = [*sequence, current]
    return PhaseDetail(
        current=current,
        sequence=tuple(sequence),
        checks=checks,
        blocked=any(not c.ok for c in checks),
    )


def phase_sequence(root: Path) -> list[str]:
    """Ordered phase backbone for the project's execution mode; falls back to
    the standard mode, then to the recognised-phase union when no config is
    present."""
    modes = read_workflow_modes(root)
    mode = read_execution_mode(root) or "standard"
    phases = [
        name
        for p in modes.get(mode) or modes.get("standard") or []
        if isinstance(name := p.get("phase"), str) and name
    ]
    return phases or list(PHASES)


def collect_phase(root: Path, /, **_opts: Any) -> View:
    """SDLC phase backbone with the current phase highlighted: green when its
    gate checks all pass, red (blocked) when any fail — mirroring phase status."""
    current, checks = evaluate_phase(root)
    blocked = any(not ok for _, ok, _ in checks)
    highlight = current if current in PHASES else None
    sequence = phase_sequence(root)
    if highlight and highlight not in sequence:
        sequence = [*sequence, highlight]
    nodes = tuple(
        Node(
            p,
            label=p,
            status=(Status.MISSING if blocked else Status.OK) if p == highlight else None,
        )
        for p in sequence
    )
    edges = tuple(Edge(sequence[i], sequence[i + 1]) for i in range(len(sequence) - 1))
    return Graph(nodes=nodes, edges=edges, direction="LR", title=f"phase: {current or 'unknown'}")


def collect_timeline(root: Path, /, **_opts: Any) -> View:
    """EVENT-LOG events folded to day precision: identical (date, label)
    entries aggregate into one event with a ``count``. Malformed lines are
    skipped, every valid event is kept (as a count contribution)."""
    counts: dict[tuple[str, str, str], int] = {}
    for rec in collect_recent_events(root, limit=0):
        ts = rec.get("ts")
        if not isinstance(ts, str):
            continue
        event = str(rec.get("event") or "event")
        ctx = rec.get("phase") or rec.get("status") or rec.get("agent") or rec.get("detail")
        # A ctx already contained in the event name adds no information
        # (e.g. session_start + "session") — keep the bare event name.
        label = event
        if isinstance(ctx, str) and ctx and ctx not in event:
            label = f"{event} {ctx}"
        key = (ts.split("T", 1)[0], event, label)
        counts[key] = counts.get(key, 0) + 1
    events = tuple(
        TimelineEvent(ts=date, label=label, category=event, count=n)
        for (date, event, label), n in counts.items()
    )
    return Timeline(events=events, title="event log")
