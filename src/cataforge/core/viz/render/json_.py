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
    """Optional keys — a node's ``data`` bag, a point's ``unit``, a series'
    ``meta`` — are omitted when unset, keeping untagged views' JSON
    byte-stable; tagged views gain purely additive keys."""
    return {
        k: v
        for k, v in items
        if not ((k in ("data", "meta") and v is None) or (k == "unit" and v == ""))
    }


def render(view: View) -> str:
    payload: dict[str, object] = {"kind": _kind(view)}
    payload.update(asdict(view, dict_factory=_drop_empty_data))
    return json.dumps(payload, ensure_ascii=False, indent=2)
