"""Semantic colour palette — the single source of truth for view styling.

Values are Mermaid ``style`` directive bodies. Collectors attach them to
nodes; the Mermaid renderer emits them verbatim and the HTML renderer maps
``fill``/``stroke`` onto node data, so one status renders as one colour in
every output format. :data:`LEGEND` drives the HTML legend strip.
"""

from __future__ import annotations

# Semantic status colours, shared across views.
GREEN_OK = "fill:#9f6,stroke:#333"  # complete / passing: impl+test, gate ok
YELLOW_PARTIAL = "fill:#ff6,stroke:#333"  # partial / stale
RED_MISSING = "fill:#f96,stroke:#333"  # missing / blocked / uncovered
RED_BROKEN = "fill:#f96,stroke:#900"  # broken reference (xref-error)
RED_CRITICAL_PATH = "fill:#f96,stroke:#333,stroke-width:2px"  # critical path
RED_CYCLE = "fill:#f00,stroke:#333,stroke-width:2px"  # dependency cycle

# Asset-type colours (assets / framework views).
AGENT_STYLE = "fill:#cde,stroke:#369"
SKILL_STYLE = "fill:#efe,stroke:#393"

# (fill hex, semantic label) — rendered as the HTML legend strip.
LEGEND: tuple[tuple[str, str], ...] = (
    ("#9f6", "完整 / 通过"),
    ("#ff6", "部分 / stale"),
    ("#f96", "缺失 / 断链 / blocked"),
)
