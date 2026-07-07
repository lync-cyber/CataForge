"""Multi-project health aggregation — one offline page, one row per root.

Each row reuses the per-project machinery unchanged (stepper, overview
groups); aggregation is a presentation layer on top, not a new data source.
"""

from __future__ import annotations

import html as _html
from pathlib import Path

from cataforge.application.viz.collectors.overview import SELF_CAUSED_LABEL
from cataforge.application.viz.html.kpi import _stepper
from cataforge.application.viz.html.page import _document
from cataforge.core.viz.model import MetricSeries


def _health_cells(root: Path) -> tuple[str, str]:
    """(断链数, self-caused 数) for one project; '—' when the source is absent."""
    from cataforge.application.viz.registry import collect_safe

    view, _ = collect_safe(root, "overview")
    groups: dict[str, dict[str, float]] = {}
    if isinstance(view, MetricSeries):
        for p in view.points:
            groups.setdefault(p.series, {})[p.label] = p.value
    links = groups.get("links")
    link_txt = (
        "—" if links is None else str(int(links.get("stale", 0) + links.get("xref_error", 0)))
    )
    decay = groups.get("decay")
    decay_txt = "0" if decay is None else str(int(decay.get(SELF_CAUSED_LABEL, 0)))
    return link_txt, decay_txt


def render_portfolio(roots: list[Path]) -> str:
    rows = []
    for root in roots:
        links, decay = _health_cells(root)
        name = root.resolve().name or str(root)  # Path(".").name is ""
        rows.append(
            f'<tr><td class="pname">{_html.escape(name)}</td>'
            f"<td>{_stepper(root)}</td>"
            f'<td class="num">{links}</td><td class="num">{decay}</td></tr>'
        )
    header = "<header><strong>CataForge portfolio</strong></header>"
    table = (
        '<div class="view"><table class="stat pf"><thead><tr>'
        "<th>项目</th><th>SDLC 阶段</th><th>断链 / stale</th><th>self-caused 纠偏</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )
    return _document("CataForge portfolio", header + table, [], [])
