"""IR forms → HTML fragments.

Each fragment builder returns ``(body_html, init_js)`` — the panel markup plus
the JS call that boots it against the vendored libraries. :func:`_fragment`
dispatches any :data:`~cataforge.core.viz.model.View` to the right builder.
"""

from __future__ import annotations

import html as _html
import importlib.resources
import json
from collections import Counter
from typing import Any

from cataforge.core.errors import CataforgeError
from cataforge.core.viz import palette
from cataforge.core.viz.model import Graph, MetricSeries, Node, Status, Timeline, View

_PKG = "cataforge.application.viz"
_CYTOSCAPE = "cytoscape.min.js"
_ECHARTS = "echarts.min.js"


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
    catalogue = graph.form == "catalogue"
    elements: list[dict[str, Any]] = []
    clusters: set[str] = set()
    for node in graph.nodes:
        # An implicit node (label=None) may still carry a display name in its
        # data bag — catalogue entries invisible to the text renderers.
        label = node.label or str((node.data or {}).get("name") or node.id)
        data: dict[str, Any] = {"id": node.id, "label": palette.marked_label(node.status, label)}
        ntype = str((node.data or {}).get("type") or "")
        # health always wins the colour channel; type fills the healthy rest
        enc = palette.encoding(node.status) if node.status else palette.type_encoding(ntype)
        if enc:
            data["bg"] = enc.fill
            data["border"] = enc.stroke
        tip = _node_tip(node)
        if tip:
            data["tip"] = tip
        # Catalogue nodes cluster into a compound parent per type, so agents /
        # skills / rules read as grouped boxes; other forms keep their topology.
        if catalogue and ntype:
            data["parent"] = f"cluster_{ntype}"
            clusters.add(ntype)
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


def _graph_fragment(graph: Graph, dom_id: str) -> tuple[str, str, bool]:
    """Pick a Graph's HTML form. Returns ``(body, init, needs_cytoscape)``:
    the collector-declared catalogue (metadata table + linked graph), an
    edgeless graph's status table (position carries no information without
    edges), or the plain zoomable graph."""
    if graph.form == "catalogue":
        body, init = _catalogue_fragment(graph, dom_id)
        return body, init, True
    if graph.nodes and not graph.edges:
        return (*_status_table_fragment(graph, dom_id), False)
    elements = _script_json(_node_data(graph))
    opts = _script_json({"dir": graph.direction})
    body = (
        '<div class="view">'
        f'<div class="toolbar"><input class="search" data-target="{dom_id}" '
        'placeholder="filter nodes…"></div>'
        f'<div id="{dom_id}" class="cy"></div></div>'
    )
    return body, f"initGraph('{dom_id}', {elements}, {opts});", True


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
    lanes = sorted({e.category for e in view.events}) or [""]
    li = {c: i for i, c in enumerate(lanes)}
    data = [
        {
            "value": [e.ts, li[e.category]],
            "name": f"{e.label} ×{e.count}" if e.count > 1 else e.label,
            "symbolSize": min(32, 9 + 3 * e.count),
        }
        for e in sorted(view.events, key=lambda e: e.ts)
    ]
    return {
        "title": {"text": view.title or "timeline"},
        "tooltip": {"trigger": "item", "formatter": "{b}"},
        "grid": {"containLabel": True, "bottom": 64},
        # a time axis keeps event density honest — a 2-day gap renders narrower
        # than a 2-week one, unlike evenly spaced date categories
        "xAxis": {"type": "time", "axisLabel": {"rotate": 45}},
        "yAxis": {"type": "category", "data": lanes},
        # a long log is scannable: brush a window on the x-axis, scroll inside it
        "dataZoom": [
            {"type": "slider", "xAxisIndex": 0, "bottom": 8},
            {"type": "inside", "xAxisIndex": 0},
        ],
        "series": [{"type": "scatter", "name": view.title or "events", "data": data}],
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
