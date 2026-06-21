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
from pathlib import Path
from typing import Any

from cataforge.core.errors import CataforgeError
from cataforge.core.viz.model import Graph, MetricSeries, Timeline, View

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
        data: dict[str, Any] = {"id": node.id, "label": node.label or node.id}
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
    elements = json.dumps(_node_data(graph), ensure_ascii=False)
    body = (
        '<div class="view">'
        f'<div class="toolbar"><input class="search" data-target="{dom_id}" '
        'placeholder="filter nodes…"></div>'
        f'<div id="{dom_id}" class="cy"></div></div>'
    )
    return body, f"initGraph('{dom_id}', {elements});"


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


def render(view: View) -> str:
    body, init, lib = _fragment(view, "view0")
    title = getattr(view, "title", "") or "viz"
    header = f"<header><strong>{_html.escape(title)}</strong></header>"
    return _document(title, header + body, [init], [lib])


def _dashboard_panel(root: Path, name: str, index: int) -> tuple[str, str | None, str | None]:
    """Render one dashboard tab. Returns ``(panel_html, init_js, lib)``;
    ``init_js`` / ``lib`` are ``None`` for empty or failed views."""
    from cataforge.application.viz.registry import collect_safe

    active = " active" if index == 0 else ""
    pid = f"panel{index}"
    view, error = collect_safe(root, name)
    if view is None:
        inner = f'<p class="error">{_html.escape(error or "")}</p>'
        return f'<section id="{pid}" class="panel{active}">{inner}</section>', None, None
    if isinstance(view, Graph) and not view.nodes:
        inner = '<p class="empty">no data</p>'
        return f'<section id="{pid}" class="panel{active}">{inner}</section>', None, None
    body, init, lib = _fragment(view, f"{pid}_v")
    return f'<section id="{pid}" class="panel{active}">{body}</section>', init, lib


def render_dashboard(root: Path, /, **_opts: Any) -> str:
    tabs: list[str] = []
    panels: list[str] = []
    inits: list[str] = []
    libs: list[str] = []
    for index, (name, label) in enumerate(_DASHBOARD_VIEWS):
        panel, init, lib = _dashboard_panel(root, name, index)
        sel = " sel" if index == 0 else ""
        tabs.append(
            f'<button class="tab{sel}" data-panel="panel{index}">{_html.escape(label)}</button>'
        )
        panels.append(panel)
        if init is not None:
            inits.append(init)
        if lib is not None and lib not in libs:
            libs.append(lib)
    header = "<header><strong>CataForge viz dashboard</strong></header>"
    nav = f'<nav class="tabs">{"".join(tabs)}</nav>'
    body = header + nav + "\n".join(panels)
    return _document("CataForge viz dashboard", body, inits, libs or [_CYTOSCAPE])


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
    "{selector:'.dim',style:{'opacity':0.12}}]"
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
    "  var ts=document.querySelectorAll('.tab');\n"
    "  for(var i=0;i<ts.length;i++){ts[i].addEventListener('click',function(){\n"
    "    showPanel(this.getAttribute('data-panel'));});}\n"
    "});\n"
)
