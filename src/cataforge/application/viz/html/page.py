"""Page assembly: single-view pages and the tabbed dashboard.

``render`` produces one standalone file per view; ``render_dashboard``
aggregates every viable view into a tabbed page that shares the two vendored
libraries. Styling comes from ``assets/dashboard.css`` (palette-derived colours
injected as CSS custom properties) and behaviour from ``assets/dashboard.js``,
both inlined so the output opens offline with zero external requests.
"""

from __future__ import annotations

import html as _html
import re
from pathlib import Path
from typing import Any

from cataforge.application.viz.html.fragments import _CYTOSCAPE, _fragment, _read_asset
from cataforge.application.viz.html.kpi import _kpi_strip, read_retro_threshold
from cataforge.core.viz import palette
from cataforge.core.viz.model import Graph, Status, View, is_empty

_DASHBOARD_CSS = "dashboard.css"
_DASHBOARD_JS = "dashboard.js"

_DASHBOARD_VIEWS: tuple[tuple[str, str], ...] = (
    ("framework", "Framework"),
    ("assets", "Assets"),
    ("trace", "Trace"),
    ("coverage", "Coverage"),
    ("arch", "Arch"),
    ("docs", "Docs"),
    ("tasks", "Tasks"),
    ("phase", "Phase"),
    ("timeline", "Timeline"),
    ("decay", "Decay"),
)


def _root_vars() -> str:
    """Palette-derived accents referenced by dashboard.css via var(--viz-*), so
    KPI tiles and node fills tell one colour story with palette as the only
    source."""
    pairs = (
        ("--viz-ok", palette.encoding(Status.OK).fill),
        ("--viz-warn", palette.encoding(Status.PARTIAL).fill),
        ("--viz-bad", palette.encoding(Status.MISSING).fill),
        ("--viz-agent", palette.TYPE_ENCODINGS["agent"].fill),
        ("--viz-skill", palette.TYPE_ENCODINGS["skill"].fill),
    )
    body = ";".join(f"{name}:{value}" for name, value in pairs)
    return f":root{{{body}}}"


def _document(title: str, body: str, inits: list[str], libs: list[str]) -> str:
    lib_blocks = "\n".join(f"<script>{_read_asset(name)}</script>" for name in libs)
    css = _root_vars() + _read_asset(_DASHBOARD_CSS)
    head = (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_html.escape(title)}</title>\n<style>{css}</style>\n</head>\n<body>\n"
    )
    scripts = f"<script>\n{_read_asset(_DASHBOARD_JS)}\n{chr(10).join(inits)}\n</script>"
    return f"{head}{body}\n{lib_blocks}\n{scripts}\n</body>\n</html>\n"


def _legend() -> str:
    """One shared legend strip: what green / yellow / red mean everywhere."""
    items = "".join(
        f'<span class="lg"><i style="background:{hexv}"></i>{_html.escape(label)}</span>'
        for hexv, label in palette.LEGEND
    )
    return f'<div class="legend">{items}</div>'


def render(view: View) -> str:
    body, init, lib = _fragment(view, "view0")
    title = getattr(view, "title", "") or "viz"
    header = f"<header><strong>{_html.escape(title)}</strong></header>"
    return _document(title, header + _legend() + body, [init], [lib] if lib else [])


_Results = dict[str, tuple[View | None, str | None]]


# Per-view guidance for a view that renders but holds no data yet.
_EMPTY_HINTS = {
    "timeline": "暂无事件 — EVENT-LOG 随工作流推进自动记录",
    "decay": "暂无纠偏记录 — 这是健康信号",
    "tasks": "暂无任务依赖 — dev-plan 任务入图或 `--edges` 传入后出现",
    "trace": "暂无可追溯实体 — `cataforge kg import` 摄取文档后出现",
    "coverage": "暂无 Feature — `cataforge kg import` 摄取 PRD 后出现",
    "arch": "暂无架构实体 — `cataforge kg import` 摄取 ARCH 后出现",
}

# Cross-view focus links: tapping a node in the source view's dashboard graph
# jumps to the target tab and focuses the same entity node. Both pairs share
# entity ids across views — a Feature id in coverage / a task id in tasks both
# reappear in the traceability chain.
_CROSS_LINKS: tuple[tuple[str, str], ...] = (("coverage", "trace"), ("tasks", "trace"))


def _inline_code(text: str) -> str:
    """Escape *text* and render its backtick spans as ``<code>``."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", _html.escape(text))


def _degraded_inner(name: str, view: View | None, error: str | None) -> str:
    """The panel body for a failed or empty view: the same actionable guidance
    ``viz status`` gives, instead of a raw error / blank chart."""
    from cataforge.application.viz.registry import short_hint

    if view is None:
        hinted = short_hint(error or "")
        if hinted.startswith("run: "):
            return (
                '<div class="empty">此视图需要的数据还未生成'
                f'<div class="hint">run: <code>{_html.escape(hinted[5:])}</code></div>'
                f'<p class="raw">{_html.escape(error or "")}</p></div>'
            )
        return f'<p class="error">{_html.escape(error or "")}</p>'
    return f'<div class="empty">{_inline_code(_EMPTY_HINTS.get(name, "暂无数据"))}</div>'


# Two tab clusters: what's the project's health vs what the framework is made of.
_HEALTH_VIEWS = frozenset({"phase", "docs", "coverage", "trace", "timeline", "decay"})
_TAB_GROUPS: tuple[tuple[str, str], ...] = (("项目健康", "health"), ("框架资产", "framework"))


def _view_group(name: str) -> str:
    return "health" if name in _HEALTH_VIEWS else "framework"


def _default_view(results: _Results, worst_view: str | None) -> str:
    """Which tab opens first: the worst KPI's view, else the first health view
    that actually has data, else the first tab."""
    order = [name for name, _ in _DASHBOARD_VIEWS]
    if worst_view and worst_view in order:
        return worst_view
    for name in order:
        if name in _HEALTH_VIEWS:
            view = results[name][0]
            if view is not None and not is_empty(view):
                return name
    return order[0]


def _dashboard_panel(
    name: str, result: tuple[View | None, str | None], active: bool
) -> tuple[str, str | None, str | None]:
    """Render one dashboard tab. Returns ``(panel_html, init_js, lib)``;
    ``init_js`` / ``lib`` are ``None`` for empty or failed views."""
    cls = " active" if active else ""
    pid = f"panel-{name}"
    view, error = result
    if view is None or is_empty(view):
        inner = _degraded_inner(name, view, error)
        return (
            f'<section id="{pid}" class="panel{cls}" role="tabpanel">{inner}</section>',
            None,
            None,
        )
    body, init, lib = _fragment(view, f"{pid}_v")
    return (
        f'<section id="{pid}" class="panel{cls}" role="tabpanel">{body}</section>',
        init,
        lib,
    )


def _grouped_nav(tabs_by_name: dict[str, str]) -> str:
    """Tabs rendered in two labelled clusters (health / framework), so a wide
    row of ten tabs reads as two scannable groups."""
    order = [name for name, _ in _DASHBOARD_VIEWS]
    blocks: list[str] = []
    for title, key in _TAB_GROUPS:
        btns = "".join(tabs_by_name[n] for n in order if _view_group(n) == key)
        blocks.append(f'<div class="tabgroup"><span class="tglabel">{title}</span>{btns}</div>')
    return f'<nav class="tabs" role="tablist">{"".join(blocks)}</nav>'


def render_dashboard(root: Path, /, **_opts: Any) -> str:
    from cataforge.application.viz.registry import collect_safe

    results: _Results = {name: collect_safe(root, name) for name, _ in _DASHBOARD_VIEWS}
    panel_ids = {name: f"panel-{name}" for name, _ in _DASHBOARD_VIEWS}
    overview, _ = collect_safe(root, "overview")
    kpis, worst_view = _kpi_strip(overview, results, panel_ids, read_retro_threshold(root))
    default_view = _default_view(results, worst_view)

    tabs_by_name: dict[str, str] = {}
    panels: list[str] = []
    panel_inits: dict[str, list[str]] = {}
    libs: list[str] = []
    graph_views: set[str] = set()
    table_views: set[str] = set()
    for name, label in _DASHBOARD_VIEWS:
        active = name == default_view
        panel, init, lib = _dashboard_panel(name, results[name], active)
        sel = " sel" if active else ""
        tabs_by_name[name] = (
            f'<button class="tab{sel}" role="tab" aria-selected="{"true" if active else "false"}"'
            f' data-panel="{panel_ids[name]}">{_html.escape(label)}</button>'
        )
        panels.append(panel)
        if init is not None:
            panel_inits[name] = [init]
            if isinstance(results[name][0], Graph):
                # a Graph with no library is one rendered as a status table
                (graph_views if lib == _CYTOSCAPE else table_views).add(name)
        if lib is not None and lib not in libs:
            libs.append(lib)
    for src, dst in _CROSS_LINKS:
        # wiring joins the source panel's register closure so it always runs
        # after that panel's own instances exist
        if src in graph_views:
            panel_inits[src].append(f"linkGraph('{panel_ids[src]}_v', '{panel_ids[dst]}');")
        elif src in table_views:
            panel_inits[src].append(f"linkTable('{panel_ids[src]}_v', '{panel_ids[dst]}');")
    nl = "\n"
    inits = [
        f"__viz.register('{panel_ids[name]}', function(){{\n{nl.join(blocks)}\n}});"
        for name, _ in _DASHBOARD_VIEWS
        if (blocks := panel_inits.get(name))
    ]

    header = "<header><strong>CataForge viz dashboard</strong></header>"
    body = header + kpis + _legend() + _grouped_nav(tabs_by_name) + "\n".join(panels)
    return _document("CataForge viz dashboard", body, inits, libs or [_CYTOSCAPE])
