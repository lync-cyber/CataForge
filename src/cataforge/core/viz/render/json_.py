"""IR → JSON. Stable external contract; ``kind`` discriminates the IR form."""

from __future__ import annotations

import json
from dataclasses import asdict

from cataforge.core.errors import CataforgeError
from cataforge.core.viz.model import Graph, MetricSeries, Timeline, View


def _kind(view: View) -> str:
    if isinstance(view, Graph):
        return "graph"
    if isinstance(view, Timeline):
        return "timeline"
    if isinstance(view, MetricSeries):
        return "metrics"
    raise CataforgeError(f"unrenderable view type: {type(view).__name__}")


def _drop_empty_data(items: list[tuple[str, object]]) -> dict[str, object]:
    """A node's ``data`` bag is optional metadata — omit the key entirely when
    unset, keeping data-less graphs' JSON byte-stable."""
    return {k: v for k, v in items if not (k == "data" and v is None)}


def render(view: View) -> str:
    payload: dict[str, object] = {"kind": _kind(view)}
    payload.update(asdict(view, dict_factory=_drop_empty_data))
    return json.dumps(payload, ensure_ascii=False, indent=2)
