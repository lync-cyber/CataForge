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
from pathlib import Path
from typing import Any

from cataforge.application.viz import palette
from cataforge.application.viz.collectors.overview import RECENT_LABEL
from cataforge.core.errors import CataforgeError
from cataforge.core.viz.model import Graph, MetricSeries, Timeline, View, is_empty

_PKG = "cataforge.application.viz"
_CYTOSCAPE = "cytoscape.min.js"
_ECHARTS = "echarts.min.js"

# Mermaid-style style-body keys → the data attribute the stylesheet reads.
_STYLE_MAP = {"fill": "bg", "stroke": "border"}

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


# --------------------------------------------------------------------------- #
# Graph → Cytoscape
# --------------------------------------------------------------------------- #
def _node_data(graph: Graph) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for node in graph.nodes:
        # An implicit node (label=None) may still carry a display name in its
        # data bag — catalogue entries invisible to the text renderers.
        label = node.label or str((node.data or {}).get("name") or node.id)
        data: dict[str, Any] = {"id": node.id, "label": label}
        for chunk in (node.style or "").split(","):
            key, sep, val = chunk.partition(":")
            attr = _STYLE_MAP.get(key.strip())
            if sep and attr:
                data[attr] = val.strip()
        elements.append({"data": data})
    for edge in graph.edges:
        data = {"source": edge.src, "target": edge.dst, "id": f"{edge.src}__{edge.dst}"}
        if edge.label:
            data["label"] = edge.label
        elements.append({"data": data})
    return elements


def _graph_fragment(graph: Graph, dom_id: str) -> tuple[str, str]:
    if any(node.data for node in graph.nodes):
        return _catalogue_fragment(graph, dom_id)
    elements = json.dumps(_node_data(graph), ensure_ascii=False)
    body = (
        '<div class="view">'
        f'<div class="toolbar"><input class="search" data-target="{dom_id}" '
        'placeholder="filter nodes…"></div>'
        f'<div id="{dom_id}" class="cy"></div></div>'
    )
    return body, f"initGraph('{dom_id}', {elements});"


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
    cells.append(f'<td class="num">{_cat_cell(data.get("lines"))}</td>')
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
    elements = json.dumps(_node_data(graph), ensure_ascii=False)
    return body, f"initCatalogue('{dom_id}', {elements});"


# --------------------------------------------------------------------------- #
# Timeline / MetricSeries → ECharts
# --------------------------------------------------------------------------- #
def _timeline_option(view: Timeline) -> dict[str, Any]:
    times = sorted({e.ts for e in view.events})
    lanes = sorted({e.category for e in view.events}) or [""]
    ti = {t: i for i, t in enumerate(times)}
    li = {c: i for i, c in enumerate(lanes)}
    data = [{"value": [ti[e.ts], li[e.category]], "name": e.label} for e in view.events]
    return {
        "title": {"text": view.title or "timeline"},
        "tooltip": {"trigger": "item", "formatter": "{b}"},
        "grid": {"containLabel": True},
        "xAxis": {"type": "category", "data": times, "axisLabel": {"rotate": 45}},
        "yAxis": {"type": "category", "data": lanes},
        "series": [{"type": "scatter", "symbolSize": 12, "data": data}],
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
    return body, f"initChart('{dom_id}', {json.dumps(option, ensure_ascii=False)});"


def _fragment(view: View, dom_id: str) -> tuple[str, str, str]:
    """Return ``(body_html, init_js, lib_name)`` for any IR form."""
    if isinstance(view, Graph):
        body, init = _graph_fragment(view, dom_id)
        return body, init, _CYTOSCAPE
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
    return _document(title, header + _legend() + body, [init], [lib])


# --------------------------------------------------------------------------- #
# Dashboard KPI strip — the overview series as clickable stat tiles
# --------------------------------------------------------------------------- #
_Results = dict[str, tuple[View | None, str | None]]


def _tile(value: str, label: str, cls: str, panel_id: str) -> str:
    return (
        f'<button class="kpi {cls}" data-panel="{panel_id}">'
        f'<span class="kpi-v">{_html.escape(value)}</span>'
        f'<span class="kpi-l">{_html.escape(label)}</span></button>'
    )


def _missing_hint(results: _Results, name: str, label: str) -> str:
    """Degraded-tile caption: reuse the detail view's own ``run …`` guidance."""
    from cataforge.application.viz.registry import short_hint

    _, error = results.get(name, (None, None))
    if error:
        hinted = short_hint(error)
        if hinted.startswith("run: "):
            return f"{label} · {hinted}"
    return f"{label} · 数据未就绪"


def _phase_tile(group: dict[str, float] | None, results: _Results, pid: str) -> str:
    if not group:
        return _tile("—", _missing_hint(results, "phase", "阶段"), "na", pid)
    total = int(group.get("total", 0))
    gate_ok = group.get("gate_ok", 0.0) >= 1.0
    name, index = next(
        ((lb, v) for lb, v in group.items() if lb not in ("total", "gate_ok")), ("?", 0.0)
    )
    value = f"{name} {int(index)}/{total}" if index else name
    label = "阶段 · 门禁通过" if gate_ok else "阶段 · 门禁受阻"
    return _tile(value, label, "ok" if gate_ok else "bad", pid)


def _docs_tile(group: dict[str, float] | None, results: _Results, pid: str) -> str:
    if not group:
        return _tile("—", _missing_hint(results, "docs", "核心文档"), "na", pid)
    total = len(group)
    present = sum(1 for v in group.values() if v >= 0.5)
    approved = sum(1 for v in group.values() if v >= 1.0)
    cls = "ok" if present == total else "warn" if present else "bad"
    return _tile(f"{present}/{total}", f"核心文档 · {approved} 已批", cls, pid)


def _coverage_tile(group: dict[str, float] | None, results: _Results, pid: str) -> str:
    if not group:
        return _tile("—", _missing_hint(results, "coverage", "Feature 覆盖"), "na", pid)
    full, partial, none = (int(group.get(k, 0)) for k in ("full", "partial", "none"))
    total = full + partial + none
    if not total:
        return _tile("—", "Feature 覆盖 · 无 Feature", "na", pid)
    cls = "ok" if full == total else "bad" if full == 0 else "warn"
    pct = round(full * 100 / total)
    return _tile(f"{pct}%", f"Feature 覆盖 · partial {partial} · none {none}", cls, pid)


def _links_tile(group: dict[str, float] | None, results: _Results, pid: str) -> str:
    if not group:
        return _tile("—", _missing_hint(results, "docs", "断链 / stale"), "na", pid)
    stale, xref = int(group.get("stale", 0)), int(group.get("xref_error", 0))
    count = stale + xref
    cls = "ok" if count == 0 else "bad" if xref else "warn"
    return _tile(str(count), f"断链 / stale · stale {stale} · xref {xref}", cls, pid)


def _decay_tile(group: dict[str, float] | None, pid: str) -> str:
    recent = int((group or {}).get(RECENT_LABEL, 0))
    total = int(sum(v for lb, v in (group or {}).items() if lb != RECENT_LABEL))
    return _tile(str(recent), f"近30天纠偏 · 累计 {total}", "ok" if recent == 0 else "warn", pid)


def _kpi_strip(overview: View | None, results: _Results, panel_ids: dict[str, str]) -> str:
    groups: dict[str, dict[str, float]] = {}
    if isinstance(overview, MetricSeries):
        for point in overview.points:
            groups.setdefault(point.series, {})[point.label] = point.value
    tiles = (
        _phase_tile(groups.get("phase"), results, panel_ids["phase"]),
        _docs_tile(groups.get("docs"), results, panel_ids["docs"]),
        _coverage_tile(groups.get("coverage"), results, panel_ids["coverage"]),
        _links_tile(groups.get("links"), results, panel_ids["docs"]),
        _decay_tile(groups.get("decay"), panel_ids["decay"]),
    )
    return f'<section class="kpis">{"".join(tiles)}</section>'


# Per-view guidance for a view that renders but holds no data yet.
_EMPTY_HINTS = {
    "timeline": "暂无事件 — EVENT-LOG 随工作流推进自动记录",
    "decay": "暂无纠偏记录 — 这是健康信号",
}

# Cross-view focus links: tapping a node in the source view's dashboard graph
# jumps to the target tab and focuses the same entity node.
_CROSS_LINKS: tuple[tuple[str, str], ...] = (("coverage", "trace"),)


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
    return f'<div class="empty">{_inline_code(_EMPTY_HINTS.get(name, "no data yet"))}</div>'


def _dashboard_panel(
    name: str, result: tuple[View | None, str | None], index: int
) -> tuple[str, str | None, str | None]:
    """Render one dashboard tab. Returns ``(panel_html, init_js, lib)``;
    ``init_js`` / ``lib`` are ``None`` for empty or failed views."""
    active = " active" if index == 0 else ""
    pid = f"panel{index}"
    view, error = result
    if view is None or is_empty(view):
        inner = _degraded_inner(name, view, error)
        return f'<section id="{pid}" class="panel{active}">{inner}</section>', None, None
    body, init, lib = _fragment(view, f"{pid}_v")
    return f'<section id="{pid}" class="panel{active}">{body}</section>', init, lib


def render_dashboard(root: Path, /, **_opts: Any) -> str:
    from cataforge.application.viz.registry import collect_safe

    results: _Results = {name: collect_safe(root, name) for name, _ in _DASHBOARD_VIEWS}
    panel_ids = {name: f"panel{index}" for index, (name, _) in enumerate(_DASHBOARD_VIEWS)}
    overview, _ = collect_safe(root, "overview")
    tabs: list[str] = []
    panels: list[str] = []
    inits: list[str] = []
    libs: list[str] = []
    graph_views: set[str] = set()
    for index, (name, label) in enumerate(_DASHBOARD_VIEWS):
        panel, init, lib = _dashboard_panel(name, results[name], index)
        sel = " sel" if index == 0 else ""
        tabs.append(
            f'<button class="tab{sel}" data-panel="panel{index}">{_html.escape(label)}</button>'
        )
        panels.append(panel)
        if init is not None:
            inits.append(init)
            if isinstance(results[name][0], Graph):
                graph_views.add(name)
        if lib is not None and lib not in libs:
            libs.append(lib)
    for src, dst in _CROSS_LINKS:
        if src in graph_views:
            inits.append(f"linkGraph('{panel_ids[src]}_v', '{panel_ids[dst]}');")
    header = "<header><strong>CataForge viz dashboard</strong></header>"
    kpis = _kpi_strip(overview, results, panel_ids)
    nav = f'<nav class="tabs">{"".join(tabs)}</nav>'
    body = header + kpis + _legend() + nav + "\n".join(panels)
    return _document("CataForge viz dashboard", body, inits, libs or [_CYTOSCAPE])


# Tile accent colours track the legend's semantic order: ok / partial / missing.
_OK_HEX, _WARN_HEX, _BAD_HEX = (hexv for hexv, _ in palette.LEGEND)


def _fill_of(style: str) -> str:
    """The ``fill`` value of a Mermaid style body — keeps CSS accents on the
    same palette constants the collectors use."""
    for chunk in style.split(","):
        key, _, value = chunk.partition(":")
        if key.strip() == "fill":
            return value.strip()
    return "#ccd2da"


_CSS = (
    "body{margin:0;font-family:system-ui,Segoe UI,Arial,sans-serif;color:#222;background:#fff}"
    "header{padding:8px 14px;border-bottom:1px solid #e3e6ea;font-size:15px}"
    ".tabs{display:flex;flex-wrap:wrap;gap:4px;padding:8px 14px;background:#f7f8fa;"
    "border-bottom:1px solid #e3e6ea}"
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
    ".cat tbody tr{cursor:pointer}.cat tr.focus{background:#eef4fb}"
    ".chip{padding:1px 7px;border-radius:9px;font-size:11px;border:1px solid #ccd2da}"
    f".chip.t-agent{{background:{_fill_of(palette.AGENT_STYLE)}}}"
    f".chip.t-skill{{background:{_fill_of(palette.SKILL_STYLE)}}}"
    ".chip.t-rules{background:#f0f1f3}"
    ".fchip{padding:3px 9px;border:1px solid #ccd2da;border-radius:12px;background:#fff;"
    "cursor:pointer;font-size:12px;margin-left:6px;color:#8a9099}"
    ".fchip.on{background:#36648b;color:#fff;border-color:#36648b}"
    ".csearch{width:260px;padding:4px 8px;border:1px solid #ccd2da;border-radius:4px;"
    "font-size:13px}"
    ".maint{margin-left:10px;font-size:12px;color:#66758c}"
    ".sortable{cursor:pointer;text-decoration:underline dotted}"
    "code.path{cursor:copy;font-size:11px;background:#f5f6f8;padding:1px 4px;border-radius:3px}"
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
    "{selector:'.dim',style:{'opacity':0.12}},"
    "{selector:'.focus',style:{'border-width':3,'border-color':'#36648b'}}]"
)

_BOOTSTRAP_JS = (
    "window.__viz=window.__viz||{cy:{},ec:{}};\n"
    "function initGraph(id,elements){\n"
    "  var cy=cytoscape({container:document.getElementById(id),elements:elements,\n"
    f"    style:{_GRAPH_STYLE},\n"
    "    layout:{name:'breadthfirst',directed:true,spacingFactor:1.1,padding:12,fit:true},\n"
    "    wheelSensitivity:0.2});\n"
    "  window.__viz.cy[id]=cy;\n"
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
    "    if(types.length&&types.indexOf(r.getAttribute('data-type'))<0)return false;\n"
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
