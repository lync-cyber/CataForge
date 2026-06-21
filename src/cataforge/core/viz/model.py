"""IR data model — three closed forms every collector maps onto.

* :class:`Graph` — nodes + directed edges (trace chains, dependency graphs,
  orchestration topology).
* :class:`Timeline` — ordered time events (EVENT-LOG, correction trend).
* :class:`MetricSeries` — labelled numeric points (coverage, decay counts).

A renderer consumes a :data:`View`; it never needs to know which collector
produced it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Node:
    """A graph node. ``label`` ``None`` ⇒ implicit node (no declaration line,
    referenced only by edges). ``style`` is renderer-specific styling (e.g. a
    Mermaid ``style`` directive body like ``fill:#f96,stroke:#333``)."""

    id: str
    label: str | None = None
    style: str | None = None


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    label: str | None = None


@dataclass(frozen=True)
class Graph:
    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    direction: str = "TD"
    title: str = ""


@dataclass(frozen=True)
class TimelineEvent:
    ts: str
    label: str
    category: str = ""


@dataclass(frozen=True)
class Timeline:
    events: tuple[TimelineEvent, ...] = ()
    title: str = ""


@dataclass(frozen=True)
class MetricPoint:
    label: str
    value: float
    series: str = ""


@dataclass(frozen=True)
class MetricSeries:
    points: tuple[MetricPoint, ...] = ()
    title: str = ""


View = Graph | Timeline | MetricSeries


def is_empty(view: View) -> bool:
    """Whether *view* carries no data — an empty graph, timeline, or series.
    Renders fine but shows nothing; callers surface this as a distinct state."""
    if isinstance(view, Graph):
        return not view.nodes
    if isinstance(view, Timeline):
        return not view.events
    return not view.points
