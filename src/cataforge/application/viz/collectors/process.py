"""Process views: SDLC phase progression + EVENT-LOG timeline.

``phase`` reuses :func:`evaluate_phase` so the graph's blocked/ok styling tracks
``cataforge phase status`` exactly; the phase backbone comes from the standard
mode's workflow config. ``timeline`` reuses the fault-tolerant EVENT-LOG reader
(malformed lines are skipped, never dropped silently from valid ones).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cataforge.application.feedback.collectors import collect_recent_events
from cataforge.application.phase import evaluate_phase
from cataforge.core.phases import PHASES
from cataforge.core.viz.model import Edge, Graph, Node, Timeline, TimelineEvent, View
from cataforge.runtime.skill.builtins.framework_review._framework_data import read_workflow_modes

_OK_STYLE = "fill:#9f6,stroke:#333"
_BLOCKED_STYLE = "fill:#f96,stroke:#333"


def _phase_sequence(root: Path) -> list[str]:
    """Ordered phase backbone from the standard mode's workflow config; falls
    back to the recognised-phase union when no config is present."""
    phases = [
        name
        for p in read_workflow_modes(root).get("standard") or []
        if isinstance(name := p.get("phase"), str) and name
    ]
    return phases or list(PHASES)


def collect_phase(root: Path, /, **_opts: Any) -> View:
    """SDLC phase backbone with the current phase highlighted: green when its
    gate checks all pass, red (blocked) when any fail — mirroring phase status."""
    current, checks = evaluate_phase(root)
    blocked = any(not ok for _, ok, _ in checks)
    highlight = current if current in PHASES else None
    sequence = _phase_sequence(root)
    if highlight and highlight not in sequence:
        sequence = [*sequence, highlight]
    nodes = tuple(
        Node(
            p,
            label=p,
            style=(_BLOCKED_STYLE if blocked else _OK_STYLE) if p == highlight else None,
        )
        for p in sequence
    )
    edges = tuple(Edge(sequence[i], sequence[i + 1]) for i in range(len(sequence) - 1))
    return Graph(nodes=nodes, edges=edges, direction="LR", title=f"phase: {current or 'unknown'}")


def collect_timeline(root: Path, /, **_opts: Any) -> View:
    """EVENT-LOG events as a timeline; malformed lines are skipped, every valid
    event is kept."""
    events: list[TimelineEvent] = []
    for rec in collect_recent_events(root, limit=0):
        ts = rec.get("ts")
        if not isinstance(ts, str):
            continue
        event = str(rec.get("event") or "event")
        ctx = rec.get("phase") or rec.get("status") or rec.get("agent") or rec.get("detail")
        label = f"{event} {ctx}" if isinstance(ctx, str) and ctx else event
        events.append(TimelineEvent(ts=ts, label=label, category=event))
    return Timeline(events=tuple(events), title="event log")
