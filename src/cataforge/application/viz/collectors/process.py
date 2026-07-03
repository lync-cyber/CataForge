"""Process views: SDLC phase progression + EVENT-LOG timeline.

``phase`` reuses :func:`evaluate_phase` so the graph's blocked/ok styling tracks
``cataforge phase status`` exactly; the phase backbone comes from the project's
execution mode (falling back to standard). ``timeline`` reuses the
fault-tolerant EVENT-LOG reader (malformed lines are skipped, never dropped
silently from valid ones).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cataforge.adapter.platform.registry import read_execution_mode
from cataforge.application.feedback.collectors import collect_recent_events
from cataforge.application.phase import evaluate_phase
from cataforge.core.phases import PHASES
from cataforge.core.viz.model import Edge, Graph, Node, Status, Timeline, TimelineEvent, View
from cataforge.runtime.skill.builtins.framework_review._framework_data import read_workflow_modes


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
