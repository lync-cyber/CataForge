"""Semantic status → visual encoding — the single source of truth.

Each :class:`~cataforge.core.viz.model.Status` maps to one :class:`Encoding`:
a colourblind-safe fill/stroke pair (ColorBrewer RdYlBu endpoints — blue =
good, orange = bad — distinguishable under deuteranopia, unlike red/green)
plus a textual ``marker`` prefixed to node labels, so every status stays
readable when colour is unavailable. :data:`LEGEND` derives from the same
table; a status renders identically in every output format.
"""

from __future__ import annotations

from dataclasses import dataclass

from cataforge.core.viz.model import Status


@dataclass(frozen=True)
class Encoding:
    """One status's visual vocabulary across renderers."""

    fill: str
    stroke: str
    stroke_width: int = 1
    marker: str = ""  # textual redundancy prefix; "" = none
    legend: str = ""  # legend label; "" = excluded from the legend strip


ENCODINGS: dict[Status, Encoding] = {
    Status.OK: Encoding("#91bfdb", "#333", marker="✓", legend="完整 / 通过"),
    Status.PARTIAL: Encoding("#ffffbf", "#333", marker="◐", legend="部分 / stale"),
    Status.MISSING: Encoding("#fc8d59", "#333", marker="✗", legend="缺失 / blocked"),
    Status.BROKEN: Encoding("#fc8d59", "#7f2704", 2, marker="⚠", legend="断链"),
    Status.CYCLE: Encoding("#fc8d59", "#d7301f", 2, marker="⟳", legend="依赖环"),
    Status.CRITICAL_PATH: Encoding("#e0f3f8", "#4575b4", 2, marker="★", legend="关键路径"),
}

# Asset-kind → visual encoding: the orthogonal colour channel for what a node
# *is* (its ``data["type"]``), distinct from how healthy it is. Health always
# wins — a renderer applies a type encoding only when the node has no status.
TYPE_ENCODINGS: dict[str, Encoding] = {
    "orchestrator": Encoding("#dbe7f3", "#36648b"),
    "phase": Encoding("#e6e2f0", "#6a5f92"),
    "agent": Encoding("#cde", "#369"),
    "skill": Encoding("#efe", "#393"),
    "rules": Encoding("#f0f1f3", "#8a9099"),
}

# (fill hex, semantic label) for statuses that carry a legend entry.
LEGEND: tuple[tuple[str, str], ...] = tuple(
    (enc.fill, enc.legend) for enc in ENCODINGS.values() if enc.legend
)


def encoding(status: Status) -> Encoding:
    return ENCODINGS[status]


def type_encoding(type_name: str) -> Encoding | None:
    return TYPE_ENCODINGS.get(type_name)


def _style_body(enc: Encoding) -> str:
    body = f"fill:{enc.fill},stroke:{enc.stroke}"
    if enc.stroke_width > 1:
        body += f",stroke-width:{enc.stroke_width}px"
    return body


def mermaid_style(status: Status) -> str:
    """The Mermaid ``style`` directive body for *status*."""
    return _style_body(ENCODINGS[status])


def mermaid_type_style(type_name: str) -> str | None:
    """The Mermaid ``style`` directive body for an asset kind, if encoded."""
    enc = TYPE_ENCODINGS.get(type_name)
    return _style_body(enc) if enc else None


def marked_label(status: Status | None, label: str) -> str:
    """*label* prefixed with the status marker, when it has one."""
    marker = ENCODINGS[status].marker if status else ""
    return f"{marker} {label}" if marker else label
