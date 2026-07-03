"""IR → single self-contained HTML.

``Graph`` → Cytoscape.js (zoom / pan / filter); ``Timeline`` / ``MetricSeries``
→ ECharts. The vendored JS is read from ``assets/`` and inlined, so the output
opens offline with zero external requests. ``render`` produces one standalone
file per view; ``render_dashboard`` aggregates every viable view into a tabbed
page that shares the two libraries.
"""

from __future__ import annotations

import html as _html
import importlib.resources
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from cataforge.application.viz.collectors.overview import CURRENT_PREFIX, SELF_CAUSED_LABEL
from cataforge.core.errors import CataforgeError
from cataforge.core.viz import palette
from cataforge.core.viz.model import Graph, MetricSeries, Node, Status, Timeline, View, is_empty

_PKG = "cataforge.application.viz"
_CYTOSCAPE = "cytoscape.min.js"
_ECHARTS = "echarts.min.js"

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


def _read_asset(name: str) -> str:
    return (importlib.resources.files(_PKG) / "assets" / name).read_text()


def _script_json(value: Any) -> str:
    """``json.dumps`` for embedding inside a ``<script>`` block: ``</`` is
    escaped so data text containing ``</script>`` cannot terminate the block
    (labels may carry arbitrary project text, e.g. the 当前阶段 value)."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


# --------------------------------------------------------------------------- #
# Graph → Cytoscape
# --------------------------------------------------------------------------- #
# data-bag keys the tooltip projects, in display order — a stable subset so a
# catalogue's full metadata bag doesn't dump every field into the hover card.
_TIP_KEYS = ("issue", "description", "hint", "path")


def _node_tip(node: Node) -> str | None:
    """Details-on-demand text for a node: its semantic status plus the acted-on
    fields of its data bag (the gap, the ``run:`` remediation, the source path).
    ``None`` when the node carries nothing worth a hover card."""
    lines: list[str] = []
    if node.status:
        enc = palette.encoding(node.status)
        lines.append(f"{enc.marker} {node.status.value}".strip())
    data = node.data or {}
    lines.extend(str(data[k]) for k in _TIP_KEYS if data.get(k))
    return "\n".join(lines) or None


def _node_data(graph: Graph) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    clusters: set[str] = set()
    for node in graph.nodes:
        # An implicit node (label=None) may still carry a display name in its
        # data bag — catalogue entries invisible to the text renderers.
        label = node.label or str((node.data or {}).get("name") or node.id)
        data: dict[str, Any] = {"id": node.id, "label": palette.marked_label(node.status, label)}
        if node.status:
            enc = palette.encoding(node.status)
            data["bg"] = enc.fill
            data["border"] = enc.stroke
        tip = _node_tip(node)
        if tip:
            data["tip"] = tip
        # Catalogue nodes (those carrying a type) cluster into a compound parent
        # per type, so agents / skills / rules read as three grouped boxes.
        ntype = (node.data or {}).get("type")
        if ntype:
            data["parent"] = f"cluster_{ntype}"
            clusters.add(str(ntype))
        elements.append({"data": data})
    for edge in graph.edges:
        edata: dict[str, Any] = {
            "source": edge.src,
            "target": edge.dst,
            "id": f"{edge.src}__{edge.dst}",
        }
        if edge.label:
            edata["label"] = edge.label
        elements.append({"data": edata})
    parents = [{"data": {"id": f"cluster_{c}", "label": c}} for c in sorted(clusters)]
    return parents + elements


def _is_catalogue(graph: Graph) -> bool:
    """A graph is an asset catalogue only when a node's data bag carries a
    ``type`` (agent/skill/rules) — the shape ``_cat_row`` expects. A data bag
    holding only a remediation ``hint`` (docs / coverage) is *not* a catalogue,
    so it renders as a normal graph / status table with the hint projected."""
    return any((node.data or {}).get("type") for node in graph.nodes)


def _graph_fragment(graph: Graph, dom_id: str) -> tuple[str, str, bool]:
    """Pick a Graph's HTML form. Returns ``(body, init, needs_cytoscape)``:
    an asset catalogue (metadata table + linked graph), an edgeless graph's
    status table (position carries no information without edges), or the plain
    zoomable graph."""
    if _is_catalogue(graph):
        body, init = _catalogue_fragment(graph, dom_id)
        return body, init, True
    if graph.nodes and not graph.edges:
        return (*_status_table_fragment(graph, dom_id), False)
    elements = _script_json(_node_data(graph))
    body = (
        '<div class="view">'
        f'<div class="toolbar"><input class="search" data-target="{dom_id}" '
        'placeholder="filter nodes…"></div>'
        f'<div id="{dom_id}" class="cy"></div></div>'
    )
    return body, f"initGraph('{dom_id}', {elements});", True


# --------------------------------------------------------------------------- #
# Edgeless status graph → sorted table + constituency bar
# --------------------------------------------------------------------------- #
# Anomaly-first ordering: the states a reader must act on come first.
_STATUS_ORDER: dict[Status, int] = {
    Status.CYCLE: 0,
    Status.BROKEN: 1,
    Status.MISSING: 2,
    Status.PARTIAL: 3,
    Status.CRITICAL_PATH: 4,
    Status.OK: 5,
    Status.AGENT: 6,
    Status.SKILL: 7,
}


def _status_rank(status: Status | None) -> int:
    return _STATUS_ORDER.get(status, 99) if status else 99


def _status_badge(status: Status | None) -> str:
    if status is None:
        return '<span class="sbadge none">—</span>'
    enc = palette.encoding(status)
    return (
        f'<span class="sbadge" style="background:{enc.fill};border-color:{enc.stroke}">'
        f"{enc.marker} {_html.escape(status.value)}</span>"
    )


def _row_hint(node: Node) -> str:
    """Inline remediation suffix for a status-table row: the same ``run:`` outlet
    the graph tooltip shows, so the table fallback keeps the action affordance."""
    data = node.data or {}
    hint = str(data.get("hint") or "")
    if not hint:
        return ""
    issue = _html.escape(str(data.get("issue") or ""))
    return f' <span class="rhint" title="{issue}">{_html.escape(hint)}</span>'


def _status_row(node: Node) -> str:
    label = node.label or str((node.data or {}).get("name") or node.id)
    sval = node.status.value if node.status else ""
    return (
        f'<tr data-node="{_html.escape(node.id)}" data-status="{_html.escape(sval)}">'
        f"<td>{_status_badge(node.status)}</td>"
        f"<td>{_html.escape(label)}{_row_hint(node)}</td></tr>"
    )


def _constituency_bar(graph: Graph) -> str:
    counts = Counter(n.status for n in graph.nodes if n.status)
    if not counts:
        return ""
    segments = "".join(
        f'<span class="seg" style="background:{palette.encoding(status).fill};flex:{count}" '
        f'title="{_html.escape(status.value)}: {count}">{count}</span>'
        for status, count in sorted(counts.items(), key=lambda kv: _status_rank(kv[0]))
    )
    return f'<div class="cbar">{segments}</div>'


def _status_table_fragment(graph: Graph, dom_id: str) -> tuple[str, str]:
    """An edgeless graph as an anomaly-first table + constituency bar. Static
    (no init JS); cross-view linking is wired separately via ``linkTable``."""
    rows = "".join(
        _status_row(node)
        for node in sorted(graph.nodes, key=lambda n: (_status_rank(n.status), n.label or n.id))
    )
    table = (
        f'<table class="stat" id="{dom_id}_tbl"><thead><tr><th>状态</th><th>节点</th></tr>'
        f"</thead><tbody>{rows}</tbody></table>"
    )
    body = (
        f'<div class="view stat-view">{_constituency_bar(graph)}'
        f'<div class="stat-wrap">{table}</div></div>'
    )
    return body, ""


# --------------------------------------------------------------------------- #
# Graph with node metadata → catalogue: filterable table + linked graph
# --------------------------------------------------------------------------- #
_CAT_COLUMNS = ("name", "type", "description", "depends", "tools", "model")


def _cat_cell(value: object) -> str:
    return _html.escape(str(value)) if value not in (None, "") else "—"


def _cat_row(node_id: str, data: dict[str, Any]) -> str:
    kind = str(data.get("type") or "")
    maint = "1" if data.get("maintainer_only") else "0"
    cells = [
        f"<td>{_cat_cell(data.get('name'))}</td>",
        f'<td><span class="chip t-{_html.escape(kind)}">{_cat_cell(kind)}</span></td>',
    ]
    cells.extend(f'<td class="desc">{_cat_cell(data.get(col))}</td>' for col in _CAT_COLUMNS[2:])
    lines_cls = "num vwarn" if data.get("lines_warn") else "num"
    cells.append(f'<td class="{lines_cls}">{_cat_cell(data.get("lines"))}</td>')
    cells.append(f'<td class="num">{_cat_cell(data.get("est_tokens"))}</td>')
    path = str(data.get("path") or "")
    path_cell = (
        f'<code class="path" title="点击复制路径">{_html.escape(path)}</code>' if path else "—"
    )
    cells.append(f"<td>{path_cell}</td>")
    return (
        f'<tr data-node="{_html.escape(node_id)}" data-type="{_html.escape(kind)}" '
        f'data-maint="{maint}">{"".join(cells)}</tr>'
    )


def _catalogue_fragment(graph: Graph, dom_id: str) -> tuple[str, str]:
    """Asset catalogue: toolbar (search / type chips / maintainer toggle) +
    metadata table + the dependency graph, cross-linked by node id."""
    entries = [(node.id, dict(node.data)) for node in graph.nodes if node.data]
    kinds = sorted({str(d.get("type") or "") for _, d in entries})
    has_maint = any(d.get("maintainer_only") for _, d in entries)

    chips = "".join(
        f'<button class="fchip on" data-type="{_html.escape(k)}">{_html.escape(k)}</button>'
        for k in kinds
    )
    maint_toggle = (
        f'<label class="maint"><input type="checkbox" id="{dom_id}_maint">含 maintainer-only'
        "</label>"
        if has_maint
        else ""
    )
    toolbar = (
        '<div class="toolbar">'
        f'<input class="csearch" id="{dom_id}_q" placeholder="搜索名称 / 描述 / 依赖 / 工具…">'
        f"{chips}{maint_toggle}</div>"
    )
    head = (
        "<tr><th>name</th><th>type</th><th>描述</th><th>depends</th><th>tools</th>"
        f'<th>model</th><th class="num">行数</th>'
        f'<th class="num sortable" id="{dom_id}_tok" title="点击按体量排序">est_tokens</th>'
        "<th>path</th></tr>"
    )
    rows = "".join(_cat_row(node_id, data) for node_id, data in entries)
    table = (
        f'<div class="cat-wrap"><table class="cat" id="{dom_id}_tbl">'
        f"<thead>{head}</thead><tbody>{rows}</tbody></table></div>"
    )
    body = f'<div class="view cat-view">{toolbar}{table}<div id="{dom_id}" class="cy"></div></div>'
    elements = _script_json(_node_data(graph))
    return body, f"initCatalogue('{dom_id}', {elements});"


# --------------------------------------------------------------------------- #
# Timeline / MetricSeries → ECharts
# --------------------------------------------------------------------------- #
def _timeline_option(view: Timeline) -> dict[str, Any]:
    times = sorted({e.ts for e in view.events})
    lanes = sorted({e.category for e in view.events}) or [""]
    ti = {t: i for i, t in enumerate(times)}
    li = {c: i for i, c in enumerate(lanes)}
    data = [
        {
            "value": [ti[e.ts], li[e.category]],
            "name": f"{e.label} ×{e.count}" if e.count > 1 else e.label,
            "symbolSize": min(32, 9 + 3 * e.count),
        }
        for e in view.events
    ]
    return {
        "title": {"text": view.title or "timeline"},
        "tooltip": {"trigger": "item", "formatter": "{b}"},
        "grid": {"containLabel": True, "bottom": 64},
        "xAxis": {"type": "category", "data": times, "axisLabel": {"rotate": 45}},
        "yAxis": {"type": "category", "data": lanes},
        # a long log is scannable: brush a window on the x-axis, scroll inside it
        "dataZoom": [
            {"type": "slider", "xAxisIndex": 0, "bottom": 8},
            {"type": "inside", "xAxisIndex": 0},
        ],
        "series": [{"type": "scatter", "data": data}],
    }


def _metric_option(view: MetricSeries) -> dict[str, Any]:
    labels: list[str] = []
    series_names: list[str] = []
    for p in view.points:
        if p.label not in labels:
            labels.append(p.label)
        if p.series not in series_names:
            series_names.append(p.series)
    cells = {(p.series, p.label): p.value for p in view.points}
    series = [
        {"name": sn or "value", "type": "bar", "data": [cells.get((sn, lb)) for lb in labels]}
        for sn in series_names
    ]
    return {
        "title": {"text": view.title or "metrics"},
        "tooltip": {"trigger": "axis"},
        "legend": {"show": len(series_names) > 1},
        "grid": {"containLabel": True},
        "xAxis": {"type": "category", "data": labels, "axisLabel": {"rotate": 30}},
        "yAxis": {"type": "value"},
        "series": series,
    }


def _chart_fragment(view: Timeline | MetricSeries, dom_id: str) -> tuple[str, str]:
    option = _timeline_option(view) if isinstance(view, Timeline) else _metric_option(view)
    body = f'<div class="view"><div id="{dom_id}" class="chart"></div></div>'
    return body, f"initChart('{dom_id}', {_script_json(option)});"


def _fragment(view: View, dom_id: str) -> tuple[str, str, str | None]:
    """Return ``(body_html, init_js, lib_name)`` for any IR form. ``lib_name``
    is ``None`` when the fragment needs no library (an edgeless status table)."""
    if isinstance(view, Graph):
        body, init, needs_cy = _graph_fragment(view, dom_id)
        return body, init, (_CYTOSCAPE if needs_cy else None)
    if isinstance(view, (Timeline, MetricSeries)):
        body, init = _chart_fragment(view, dom_id)
        return body, init, _ECHARTS
    raise CataforgeError(f"unrenderable view type: {type(view).__name__}")


# --------------------------------------------------------------------------- #
# Page assembly
# --------------------------------------------------------------------------- #
def _document(title: str, body: str, inits: list[str], libs: list[str]) -> str:
    lib_blocks = "\n".join(f"<script>{_read_asset(name)}</script>" for name in libs)
    head = (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_html.escape(title)}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n"
    )
    scripts = f"<script>\n{_BOOTSTRAP_JS}\n{chr(10).join(inits)}\n</script>"
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


# --------------------------------------------------------------------------- #
# Dashboard KPI strip — the overview series as clickable stat tiles
# --------------------------------------------------------------------------- #
_Results = dict[str, tuple[View | None, str | None]]


# cls → severity rank; the highest-ranked tile decides which tab opens first.
_CLS_RANK = {"na": 0, "ok": 0, "warn": 1, "bad": 2}


def _tile(value: str, label: str, cls: str, panel_id: str) -> tuple[str, int]:
    """A KPI tile plus its severity rank, so the strip can point the default
    tab at the worst signal instead of always opening the first view."""
    html_ = (
        f'<button class="kpi {cls}" data-panel="{panel_id}">'
        f'<span class="kpi-v">{_html.escape(value)}</span>'
        f'<span class="kpi-l">{_html.escape(label)}</span></button>'
    )
    return html_, _CLS_RANK.get(cls, 0)


def _missing_hint(results: _Results, name: str, label: str) -> str:
    """Degraded-tile caption: reuse the detail view's own ``run …`` guidance."""
    from cataforge.application.viz.registry import short_hint

    _, error = results.get(name, (None, None))
    if error:
        hinted = short_hint(error)
        if hinted.startswith("run: "):
            return f"{label} · {hinted}"
    return f"{label} · 数据未就绪"


def _phase_tile(group: dict[str, float] | None, results: _Results, pid: str) -> tuple[str, int]:
    if not group:
        return _tile("—", _missing_hint(results, "phase", "阶段"), "na", pid)
    if group.get("applicable", 1.0) < 1.0:
        return _tile("N/A", "SDLC 阶段 · 本项目不适用", "na", pid)
    total = int(group.get("total", 0))
    gate_ok = group.get("gate_ok", 0.0) >= 1.0
    name, index = next(
        (
            (lb[len(CURRENT_PREFIX) :], v)
            for lb, v in group.items()
            if lb.startswith(CURRENT_PREFIX)
        ),
        ("?", 0.0),
    )
    value = f"{name} {int(index)}/{total}" if index else name
    label = "阶段 · 门禁通过" if gate_ok else "阶段 · 门禁受阻"
    return _tile(value, label, "ok" if gate_ok else "bad", pid)


def _docs_tile(group: dict[str, float] | None, results: _Results, pid: str) -> tuple[str, int]:
    if not group:
        return _tile("—", _missing_hint(results, "docs", "核心文档"), "na", pid)
    total = len(group)
    present = sum(1 for v in group.values() if v >= 0.5)
    approved = sum(1 for v in group.values() if v >= 1.0)
    cls = "ok" if present == total else "warn" if present else "bad"
    return _tile(f"{present}/{total}", f"核心文档 · {approved} 已批", cls, pid)


def _coverage_tile(group: dict[str, float] | None, results: _Results, pid: str) -> tuple[str, int]:
    if not group:
        return _tile("—", _missing_hint(results, "coverage", "Feature 覆盖"), "na", pid)
    full, partial, none = (int(group.get(k, 0)) for k in ("full", "partial", "none"))
    total = full + partial + none
    if not total:
        return _tile("—", "Feature 覆盖 · 无 Feature", "na", pid)
    cls = "ok" if full == total else "bad" if full == 0 else "warn"
    pct = round(full * 100 / total)
    gap = total - full  # Features short of the 100% target line
    return _tile(f"{pct}%", f"Feature 覆盖 · 缺口 {gap} → 100%", cls, pid)


def _links_tile(group: dict[str, float] | None, results: _Results, pid: str) -> tuple[str, int]:
    if not group:
        return _tile("—", _missing_hint(results, "docs", "断链 / stale"), "na", pid)
    stale, xref = int(group.get("stale", 0)), int(group.get("xref_error", 0))
    count = stale + xref
    cls = "ok" if count == 0 else "bad" if xref else "warn"
    return _tile(str(count), f"断链 / stale · stale {stale} · xref {xref}", cls, pid)


_MONTH_RE = re.compile(r"\d{4}-\d{2}")


def _month_over_month(group: dict[str, float]) -> str:
    """↑ / ↓ / → for the two most recent monthly correction counts — direction,
    not just a running total, so a spike or a cooldown is visible at a glance."""
    months = sorted(k for k in group if _MONTH_RE.fullmatch(k))
    if len(months) < 2:
        return "→"
    cur, prev = group[months[-1]], group[months[-2]]
    return "↑" if cur > prev else "↓" if cur < prev else "→"


def _decay_tile(group: dict[str, float] | None, pid: str, threshold: int) -> tuple[str, int]:
    """Self-caused corrections against the retrospective trigger line: ``N/阈值``
    plus month-over-month direction. Red once the retro line is reached."""
    g = group or {}
    self_caused = int(g.get(SELF_CAUSED_LABEL, 0))
    cls = "bad" if self_caused >= threshold else "warn" if self_caused else "ok"
    arrow = _month_over_month(g)
    return _tile(f"{self_caused}/{threshold}", f"self-caused → retro · 环比{arrow}", cls, pid)


def _kpi_strip(
    overview: View | None, results: _Results, panel_ids: dict[str, str], retro_threshold: int
) -> tuple[str, str | None]:
    """Return ``(strip_html, worst_view)``. ``worst_view`` is the view name of
    the highest-severity tile (``None`` when every tile is ok/na), so the caller
    can open the tab that most needs attention."""
    groups: dict[str, dict[str, float]] = {}
    if isinstance(overview, MetricSeries):
        for point in overview.points:
            groups.setdefault(point.series, {})[point.label] = point.value
    # (tile, the view its worst state should open)
    tiles = [
        (_phase_tile(groups.get("phase"), results, panel_ids["phase"]), "phase"),
        (_docs_tile(groups.get("docs"), results, panel_ids["docs"]), "docs"),
        (_coverage_tile(groups.get("coverage"), results, panel_ids["coverage"]), "coverage"),
        (_links_tile(groups.get("links"), results, panel_ids["docs"]), "docs"),
        (_decay_tile(groups.get("decay"), panel_ids["decay"], retro_threshold), "decay"),
    ]
    html_ = "".join(tile for (tile, _rank), _view in tiles)
    worst_rank = max((rank for (_tile_html, rank), _view in tiles), default=0)
    worst_view = next(
        (view for (_tile_html, rank), view in tiles if rank == worst_rank and rank > 0), None
    )
    return f'<section class="kpis">{html_}</section>', worst_view


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


def _default_index(results: _Results, worst_view: str | None) -> int:
    """Which tab opens first: the worst KPI's view, else the first health view
    that actually has data, else the first tab."""
    order = [name for name, _ in _DASHBOARD_VIEWS]
    if worst_view and worst_view in order:
        return order.index(worst_view)
    for i, name in enumerate(order):
        if name in _HEALTH_VIEWS:
            view = results[name][0]
            if view is not None and not is_empty(view):
                return i
    return 0


def _dashboard_panel(
    name: str, result: tuple[View | None, str | None], index: int, active: bool
) -> tuple[str, str | None, str | None]:
    """Render one dashboard tab. Returns ``(panel_html, init_js, lib)``;
    ``init_js`` / ``lib`` are ``None`` for empty or failed views."""
    cls = " active" if active else ""
    pid = f"panel{index}"
    view, error = result
    if view is None or is_empty(view):
        inner = _degraded_inner(name, view, error)
        return f'<section id="{pid}" class="panel{cls}">{inner}</section>', None, None
    body, init, lib = _fragment(view, f"{pid}_v")
    return f'<section id="{pid}" class="panel{cls}">{body}</section>', init, lib


def _grouped_nav(tabs_by_name: dict[str, str]) -> str:
    """Tabs rendered in two labelled clusters (health / framework), so a wide
    row of ten tabs reads as two scannable groups."""
    order = [name for name, _ in _DASHBOARD_VIEWS]
    blocks: list[str] = []
    for title, key in _TAB_GROUPS:
        btns = "".join(tabs_by_name[n] for n in order if _view_group(n) == key)
        blocks.append(f'<div class="tabgroup"><span class="tglabel">{title}</span>{btns}</div>')
    return f'<nav class="tabs">{"".join(blocks)}</nav>'


def render_dashboard(root: Path, /, **_opts: Any) -> str:
    from cataforge.application.viz.registry import collect_safe
    from cataforge.runtime.skill.builtins.framework_review._framework_data import (
        read_retro_self_caused_threshold,
    )

    results: _Results = {name: collect_safe(root, name) for name, _ in _DASHBOARD_VIEWS}
    panel_ids = {name: f"panel{index}" for index, (name, _) in enumerate(_DASHBOARD_VIEWS)}
    overview, _ = collect_safe(root, "overview")
    kpis, worst_view = _kpi_strip(
        overview, results, panel_ids, read_retro_self_caused_threshold(root)
    )
    default_index = _default_index(results, worst_view)

    tabs_by_name: dict[str, str] = {}
    panels: list[str] = []
    inits: list[str] = []
    libs: list[str] = []
    graph_views: set[str] = set()
    table_views: set[str] = set()
    for index, (name, label) in enumerate(_DASHBOARD_VIEWS):
        panel, init, lib = _dashboard_panel(name, results[name], index, index == default_index)
        sel = " sel" if index == default_index else ""
        tabs_by_name[name] = (
            f'<button class="tab{sel}" data-panel="panel{index}">{_html.escape(label)}</button>'
        )
        panels.append(panel)
        if init is not None:
            inits.append(init)
            if isinstance(results[name][0], Graph):
                # a Graph with no library is one rendered as a status table
                (graph_views if lib == _CYTOSCAPE else table_views).add(name)
        if lib is not None and lib not in libs:
            libs.append(lib)
    for src, dst in _CROSS_LINKS:
        if src in graph_views:
            inits.append(f"linkGraph('{panel_ids[src]}_v', '{panel_ids[dst]}');")
        elif src in table_views:
            inits.append(f"linkTable('{panel_ids[src]}_v', '{panel_ids[dst]}');")

    header = "<header><strong>CataForge viz dashboard</strong></header>"
    body = header + kpis + _legend() + _grouped_nav(tabs_by_name) + "\n".join(panels)
    return _document("CataForge viz dashboard", body, inits, libs or [_CYTOSCAPE])


# Tile accent colours share the status palette, so KPI tiles and node fills
# tell one colour story.
_OK_HEX = palette.encoding(Status.OK).fill
_WARN_HEX = palette.encoding(Status.PARTIAL).fill
_BAD_HEX = palette.encoding(Status.MISSING).fill


_CSS = (
    "body{margin:0;font-family:system-ui,Segoe UI,Arial,sans-serif;color:#222;background:#fff}"
    "header{padding:8px 14px;border-bottom:1px solid #e3e6ea;font-size:15px}"
    ".tabs{display:flex;flex-wrap:wrap;gap:14px;padding:8px 14px;background:#f7f8fa;"
    "border-bottom:1px solid #e3e6ea}"
    ".tabgroup{display:flex;flex-wrap:wrap;align-items:center;gap:4px}"
    ".tglabel{font-size:11px;color:#8a9099;margin-right:2px;font-weight:600}"
    ".tab{padding:4px 10px;border:1px solid #ccd2da;border-radius:4px;background:#fff;"
    "cursor:pointer;font-size:13px}"
    ".tab.sel{background:#36648b;color:#fff;border-color:#36648b}"
    ".view{padding:8px 14px}.toolbar{margin-bottom:6px}"
    ".search{width:240px;padding:4px 8px;border:1px solid #ccd2da;border-radius:4px;font-size:13px}"
    ".cy,.chart{width:100%;height:78vh;border:1px solid #eef1f4}"
    ".panel{display:none}.panel.active{display:block}"
    ".empty{padding:28px;color:#8a9099}.error{padding:28px;color:#b00020;white-space:pre-wrap}"
    ".empty code{background:#f5f6f8;padding:2px 8px;border-radius:4px;color:#36648b}"
    ".empty .hint{margin-top:10px}"
    ".empty .raw{margin-top:12px;font-size:11px;color:#c3c9d1}"
    ".kpis{display:flex;flex-wrap:wrap;gap:8px;padding:10px 14px;background:#fbfcfd;"
    "border-bottom:1px solid #e3e6ea}"
    ".kpi{display:flex;flex-direction:column;align-items:flex-start;gap:2px;padding:8px 12px;"
    "min-width:130px;border:1px solid #ccd2da;border-left-width:4px;border-radius:6px;"
    "background:#fff;cursor:pointer;text-align:left}"
    ".kpi-v{font-size:18px;font-weight:600;color:#1f2d3d}"
    ".kpi-l{font-size:11px;color:#66758c}"
    f".kpi.ok{{border-left-color:{_OK_HEX}}}.kpi.warn{{border-left-color:{_WARN_HEX}}}"
    f".kpi.bad{{border-left-color:{_BAD_HEX}}}.kpi.na{{border-left-color:#ccd2da}}"
    ".legend{display:flex;flex-wrap:wrap;gap:14px;padding:6px 14px;font-size:11px;"
    "color:#66758c;border-bottom:1px solid #eef1f4}"
    ".legend .lg{display:inline-flex;align-items:center;gap:4px}"
    ".legend i{width:10px;height:10px;border:1px solid #333;border-radius:2px;"
    "display:inline-block}"
    ".cat-view .cy{height:44vh}"
    ".cat-wrap{max-height:34vh;overflow:auto;border:1px solid #eef1f4;margin-bottom:8px}"
    ".cat{width:100%;border-collapse:collapse;font-size:12px}"
    ".cat th{position:sticky;top:0;background:#f7f8fa;text-align:left;padding:5px 8px;"
    "border-bottom:1px solid #e3e6ea;white-space:nowrap}"
    ".cat td{padding:4px 8px;border-bottom:1px solid #f0f2f5;vertical-align:top}"
    ".cat td.desc{max-width:340px}"
    ".cat td.num,.cat th.num{text-align:right}"
    ".cat td.vwarn{color:#b4690e;font-weight:600}"
    ".cat tbody tr{cursor:pointer}.cat tr.focus{background:#eef4fb}"
    ".chip{padding:1px 7px;border-radius:9px;font-size:11px;border:1px solid #ccd2da}"
    f".chip.t-agent{{background:{palette.encoding(Status.AGENT).fill}}}"
    f".chip.t-skill{{background:{palette.encoding(Status.SKILL).fill}}}"
    ".chip.t-rules{background:#f0f1f3}"
    ".fchip{padding:3px 9px;border:1px solid #ccd2da;border-radius:12px;background:#fff;"
    "cursor:pointer;font-size:12px;margin-left:6px;color:#8a9099}"
    ".fchip.on{background:#36648b;color:#fff;border-color:#36648b}"
    ".csearch{width:260px;padding:4px 8px;border:1px solid #ccd2da;border-radius:4px;"
    "font-size:13px}"
    ".maint{margin-left:10px;font-size:12px;color:#66758c}"
    ".sortable{cursor:pointer;text-decoration:underline dotted}"
    "code.path{cursor:copy;font-size:11px;background:#f5f6f8;padding:1px 4px;border-radius:3px}"
    ".cbar{display:flex;height:16px;border-radius:4px;overflow:hidden;margin-bottom:10px;"
    "border:1px solid #e3e6ea}"
    ".cbar .seg{display:flex;align-items:center;justify-content:center;font-size:10px;"
    "color:#1f2d3d;min-width:16px}"
    ".stat-wrap{max-height:74vh;overflow:auto;border:1px solid #eef1f4}"
    ".stat{width:100%;border-collapse:collapse;font-size:13px}"
    ".stat th{position:sticky;top:0;background:#f7f8fa;text-align:left;padding:6px 10px;"
    "border-bottom:1px solid #e3e6ea}"
    ".stat td{padding:5px 10px;border-bottom:1px solid #f0f2f5}"
    ".stat tr.focus{background:#eef4fb}"
    ".sbadge{display:inline-block;padding:1px 8px;border-radius:9px;font-size:11px;"
    "border:1px solid #ccd2da;white-space:nowrap}"
    ".sbadge.none{background:#f0f1f3;color:#8a9099}"
    ".stat tbody tr{cursor:pointer}"
    ".rhint{margin-left:8px;font-size:11px;color:#36648b;background:#f5f6f8;"
    "padding:1px 6px;border-radius:3px;font-family:ui-monospace,Menlo,Consolas,monospace}"
    ".viztip{position:absolute;z-index:50;max-width:320px;padding:6px 9px;"
    "background:#1f2d3d;color:#f7f8fa;font-size:11px;line-height:1.5;border-radius:5px;"
    "pointer-events:none;box-shadow:0 2px 8px rgba(0,0,0,.25)}"
)

_GRAPH_STYLE = (
    "[{selector:'node',style:{'background-color':'#dfe6ee','border-color':'#7f8fa6',"
    "'border-width':1,'label':'data(label)','font-size':10,'text-valign':'center',"
    "'text-halign':'center','width':'label','height':'label','padding':'6px',"
    "'shape':'round-rectangle','color':'#1f2d3d'}},"
    "{selector:'node[bg]',style:{'background-color':'data(bg)'}},"
    "{selector:'node[border]',style:{'border-color':'data(border)','border-width':2}},"
    "{selector:'edge',style:{'width':1,'line-color':'#aab2bd','target-arrow-color':'#aab2bd',"
    "'target-arrow-shape':'triangle','curve-style':'bezier','label':'data(label)',"
    "'font-size':8,'color':'#66758c','text-background-color':'#fff','text-background-opacity':1}},"
    "{selector:':parent',style:{'background-opacity':0.06,'background-color':'#36648b',"
    "'border-color':'#c3ccd6','border-width':1,'label':'data(label)','font-size':11,"
    "'color':'#66758c','text-valign':'top','text-halign':'center','padding':'10px',"
    "'shape':'round-rectangle'}},"
    "{selector:'.dim',style:{'opacity':0.12}},"
    "{selector:'.focus',style:{'border-width':3,'border-color':'#36648b'}}]"
)

_BOOTSTRAP_JS = (
    "window.__viz=window.__viz||{cy:{},ec:{}};\n"
    "function initGraph(id,elements){\n"
    "  var compound=elements.some(function(e){return e.data&&e.data.parent;});\n"
    "  var layout=compound\n"
    "    ?{name:'cose',padding:14,fit:true,nodeDimensionsIncludeLabels:true,idealEdgeLength:60}\n"
    "    :{name:'breadthfirst',directed:true,spacingFactor:1.1,padding:12,fit:true};\n"
    "  var cy=cytoscape({container:document.getElementById(id),elements:elements,\n"
    f"    style:{_GRAPH_STYLE},\n"
    "    layout:layout,\n"
    "    wheelSensitivity:0.2});\n"
    "  window.__viz.cy[id]=cy;\n"
    "  var tip=window.__viz.tip||(window.__viz.tip=(function(){\n"
    "    var d=document.createElement('div');d.className='viztip';d.style.display='none';\n"
    "    document.body.appendChild(d);return d;})());\n"
    "  cy.on('mouseover','node',function(ev){\n"
    "    var t=ev.target.data('tip');if(!t){return;}\n"
    "    tip.innerHTML=t.split('\\n').map(function(s){\n"
    "      return s.replace(/&/g,'&amp;').replace(/</g,'&lt;');}).join('<br>');\n"
    "    tip.style.display='block';\n"
    "  });\n"
    "  cy.on('mousemove','node',function(ev){\n"
    "    tip.style.left=(ev.originalEvent.pageX+12)+'px';\n"
    "    tip.style.top=(ev.originalEvent.pageY+12)+'px';\n"
    "  });\n"
    "  cy.on('mouseout','node',function(){tip.style.display='none';});\n"
    "  var box=document.querySelector('.search[data-target=\"'+id+'\"]');\n"
    "  if(box){box.addEventListener('input',function(){\n"
    "    var q=this.value.trim().toLowerCase();\n"
    "    if(!q){cy.elements().removeClass('dim');return;}\n"
    "    cy.nodes().forEach(function(n){\n"
    "      var hit=(n.data('label')||'').toLowerCase().indexOf(q)>=0;\n"
    "      n.toggleClass('dim',!hit);});\n"
    "    cy.edges().forEach(function(e){\n"
    "      var keep=!e.source().hasClass('dim')&&!e.target().hasClass('dim');\n"
    "      e.toggleClass('dim',!keep);});\n"
    "  });}\n"
    "  return cy;\n"
    "}\n"
    "function initChart(id,option){\n"
    "  var c=echarts.init(document.getElementById(id));\n"
    "  c.setOption(option);window.__viz.ec[id]=c;return c;\n"
    "}\n"
    "function initCatalogue(id,elements){\n"
    "  var cy=initGraph(id,elements);\n"
    "  var q=document.getElementById(id+'_q');\n"
    "  var tbl=document.getElementById(id+'_tbl');\n"
    "  var maint=document.getElementById(id+'_maint');\n"
    "  var view=tbl?tbl.parentNode.parentNode:null;\n"
    "  var chips=view?view.querySelectorAll('.fchip'):[];\n"
    "  function rowVisible(r,needle,types){\n"
    "    if(r.getAttribute('data-maint')==='1'&&(!maint||!maint.checked))return false;\n"
    "    if(types.indexOf(r.getAttribute('data-type'))<0)return false;\n"
    "    return !needle||r.textContent.toLowerCase().indexOf(needle)>=0;\n"
    "  }\n"
    "  function apply(){\n"
    "    var needle=q?q.value.trim().toLowerCase():'';\n"
    "    var types=[];\n"
    "    for(var i=0;i<chips.length;i++){if(chips[i].classList.contains('on'))"
    "types.push(chips[i].getAttribute('data-type'));}\n"
    "    var rows=tbl?tbl.tBodies[0].rows:[],visible={};\n"
    "    for(var j=0;j<rows.length;j++){\n"
    "      var ok=rowVisible(rows[j],needle,types);\n"
    "      rows[j].style.display=ok?'':'none';\n"
    "      visible[rows[j].getAttribute('data-node')]=ok;\n"
    "    }\n"
    "    cy.nodes().forEach(function(n){n.toggleClass('dim',visible[n.id()]===false);});\n"
    "    cy.edges().forEach(function(e){\n"
    "      var keep=!e.source().hasClass('dim')&&!e.target().hasClass('dim');\n"
    "      e.toggleClass('dim',!keep);});\n"
    "  }\n"
    "  if(q)q.addEventListener('input',apply);\n"
    "  if(maint)maint.addEventListener('change',apply);\n"
    "  for(var c=0;c<chips.length;c++){chips[c].addEventListener('click',function(){\n"
    "    this.classList.toggle('on');apply();});}\n"
    "  function focusRow(target){\n"
    "    var rows=tbl.tBodies[0].rows;\n"
    "    for(var i=0;i<rows.length;i++){rows[i].classList.toggle('focus',rows[i]===target);}\n"
    "  }\n"
    "  if(tbl){tbl.addEventListener('click',function(ev){\n"
    "    var t=ev.target;\n"
    "    if(t.className==='path'){\n"
    "      if(navigator.clipboard&&navigator.clipboard.writeText)"
    "navigator.clipboard.writeText(t.textContent);\n"
    "      t.setAttribute('title','已复制');\n"
    "      return;\n"
    "    }\n"
    "    while(t&&t!==tbl&&!t.getAttribute('data-node'))t=t.parentNode;\n"
    "    if(!t||t===tbl)return;\n"
    "    focusRow(t);\n"
    "    var n=cy.getElementById(t.getAttribute('data-node'));\n"
    "    if(n.length){cy.elements().removeClass('focus');n.addClass('focus');cy.center(n);}\n"
    "  });}\n"
    "  cy.on('tap','node',function(ev){\n"
    "    cy.elements().removeClass('focus');ev.target.addClass('focus');\n"
    "    if(!tbl)return;\n"
    "    var rows=tbl.tBodies[0].rows;\n"
    "    for(var i=0;i<rows.length;i++){\n"
    "      if(rows[i].getAttribute('data-node')===ev.target.id()){\n"
    "        focusRow(rows[i]);rows[i].scrollIntoView({block:'nearest'});break;}}\n"
    "  });\n"
    "  var tok=document.getElementById(id+'_tok'),asc=false;\n"
    "  if(tok&&tbl){tok.addEventListener('click',function(){\n"
    "    var body=tbl.tBodies[0],rows=Array.prototype.slice.call(body.rows);\n"
    "    rows.sort(function(a,b){/* cell 7 = est_tokens */\n"
    "      var av=parseInt(a.cells[7].textContent)||0,bv=parseInt(b.cells[7].textContent)||0;\n"
    "      return asc?av-bv:bv-av;});\n"
    "    asc=!asc;\n"
    "    for(var i=0;i<rows.length;i++){body.appendChild(rows[i]);}\n"
    "  });}\n"
    "  apply();\n"
    "  return cy;\n"
    "}\n"
    "window.__viz.focus=function(pid,nid){\n"
    "  showPanel(pid);\n"
    "  var active=document.getElementById(pid);if(!active)return;\n"
    "  for(var a in window.__viz.cy){var g=window.__viz.cy[a];\n"
    "    if(active.contains(g.container())){\n"
    "      g.elements().removeClass('focus');\n"
    "      var n=g.getElementById(nid);\n"
    "      if(n.length){n.addClass('focus');g.center(n);}\n"
    "      break;}}\n"
    "};\n"
    "function linkGraph(id,targetPid){\n"
    "  var cy=window.__viz.cy[id];if(!cy)return;\n"
    "  cy.on('tap','node',function(ev){window.__viz.focus(targetPid,ev.target.id());});\n"
    "}\n"
    "function linkTable(id,targetPid){\n"
    "  var tbl=document.getElementById(id+'_tbl');if(!tbl)return;\n"
    "  tbl.addEventListener('click',function(ev){\n"
    "    var t=ev.target;\n"
    "    while(t&&t!==tbl&&!t.getAttribute('data-node'))t=t.parentNode;\n"
    "    if(!t||t===tbl)return;\n"
    "    var rows=tbl.tBodies[0].rows;\n"
    "    for(var i=0;i<rows.length;i++){rows[i].classList.toggle('focus',rows[i]===t);}\n"
    "    window.__viz.focus(targetPid,t.getAttribute('data-node'));\n"
    "  });\n"
    "}\n"
    "function showPanel(pid){\n"
    "  var ps=document.querySelectorAll('.panel');\n"
    "  for(var i=0;i<ps.length;i++){ps[i].classList.toggle('active',ps[i].id===pid);}\n"
    "  var ts=document.querySelectorAll('.tab');\n"
    "  for(var j=0;j<ts.length;j++){ts[j].classList.toggle('sel',"
    "ts[j].getAttribute('data-panel')===pid);}\n"
    "  var active=document.getElementById(pid);if(!active)return;\n"
    "  for(var a in window.__viz.cy){var g=window.__viz.cy[a];\n"
    "    if(active.contains(g.container())){g.resize();g.fit();}}\n"
    "  for(var b in window.__viz.ec){var el=document.getElementById(b);\n"
    "    if(el&&active.contains(el)){window.__viz.ec[b].resize();}}\n"
    "}\n"
    "document.addEventListener('DOMContentLoaded',function(){\n"
    "  var ts=document.querySelectorAll('[data-panel]');\n"
    "  for(var i=0;i<ts.length;i++){ts[i].addEventListener('click',function(){\n"
    "    showPanel(this.getAttribute('data-panel'));});}\n"
    "});\n"
)
