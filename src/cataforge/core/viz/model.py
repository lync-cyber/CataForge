"""IR data model — three closed forms every collector maps onto.

* :class:`Graph` — nodes + directed edges (trace chains, dependency graphs,
  orchestration topology).
* :class:`Timeline` — ordered time events (EVENT-LOG, correction trend).
* :class:`MetricSeries` — labelled numeric points (coverage, decay counts).

A renderer consumes a :data:`View`; it never needs to know which collector
produced it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    """Semantic node health. Collectors attach it; each renderer maps it to
    its own visual encoding (colour + textual marker) via
    :mod:`cataforge.core.viz.palette`, so hue is never the only channel.
    Asset kinds (agent / skill / …) are not statuses — they ride the node's
    ``data["type"]`` and colour through :data:`palette.TYPE_ENCODINGS`."""

    OK = "ok"
    PARTIAL = "partial"
    MISSING = "missing"
    BROKEN = "broken"
    CYCLE = "cycle"
    CRITICAL_PATH = "critical-path"


@dataclass(frozen=True)
class Node:
    """A graph node. ``label`` ``None`` ⇒ implicit node (no declaration line,
    referenced only by edges). ``status`` is the semantic state renderers
    encode visually. ``data`` is an optional metadata bag: text renderers
    ignore it, the JSON renderer passes it through, and rich renderers may
    project it (e.g. the HTML asset catalogue table)."""

    id: str
    label: str | None = None
    status: Status | None = None
    data: Mapping[str, object] | None = None


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    label: str | None = None


@dataclass(frozen=True)
class Graph:
    """``form`` is the collector-declared presentation intent: ``""`` renders
    by shape (graph / status table), ``"catalogue"`` requests the metadata
    table + clustered graph — renderers never sniff the intent from data."""

    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    direction: str = "TD"
    title: str = ""
    form: str = ""


@dataclass(frozen=True)
class TimelineEvent:
    """``count`` folds identical events (same ts/label/category) into one
    entry — collectors aggregate; renderers encode it (``×N`` suffix, point
    size) instead of repeating the event."""

    ts: str
    label: str
    category: str = ""
    count: int = 1


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
