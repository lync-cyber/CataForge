"""IR → single self-contained HTML.

``Graph`` → Cytoscape.js (zoom / pan / filter); ``Timeline`` / ``MetricSeries``
→ ECharts. The vendored JS is read from ``assets/`` and inlined, so the output
opens offline with zero external requests. ``render`` produces one standalone
file per view; ``render_dashboard`` aggregates every viable view into a tabbed
page that shares the two libraries.
"""

from cataforge.application.viz.html.fragments import _read_asset as _read_asset
from cataforge.application.viz.html.page import _DASHBOARD_VIEWS as _DASHBOARD_VIEWS
from cataforge.application.viz.html.page import render as render
from cataforge.application.viz.html.page import render_dashboard as render_dashboard

__all__ = ["render", "render_dashboard"]
