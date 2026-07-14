"""IR forms → HTML fragments.

Each fragment builder returns ``(body_html, init_js)`` — the panel markup plus
the JS call that boots it against the vendored libraries. :func:`_fragment`
dispatches any :data:`~cataforge.core.viz.model.View` to the right builder.
"""

from __future__ import annotations

import html as _html
import importlib.resources
import json
import math
from collections import Counter
from typing import Any

from cataforge.core.errors import CataforgeError
from cataforge.core.viz import palette
from cataforge.core.viz.model import Graph, MetricPoint, MetricSeries, Node, Status, Timeline, View

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
        if node.status:
            # semantic status travels with the element so client-side filters
            # (anomaly isolation) don't have to reverse colours into meaning
            data["status"] = node.status.value
        if node.data:
            # the full bag rides along for the side inspector's projection
            data["meta"] = {str(k): str(v) for k, v in node.data.items()}
        ntype = str((node.data or {}).get("type") or "")
        if ntype:
            data["type"] = ntype  # cytoscape-selectable: layer folding keys on it
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


def _type_chips(graph: Graph) -> str:
    """Count-badged layer chips: toggling one folds that type's nodes away,
    which is how a hundreds-of-nodes graph stays navigable."""
    counts = Counter(str((n.data or {}).get("type") or "") for n in graph.nodes)
    counts.pop("", None)
    if not counts:
        return ""
    return "".join(
        f'<button class="fchip on" data-type="{_html.escape(t)}" aria-pressed="true">'
        f"{_html.escape(t)} ({n})</button>"
        for t, n in sorted(counts.items())
    )


def _graph_fragment(graph: Graph, dom_id: str) -> tuple[str, str, bool]:
    """Pick a Graph's HTML form. Returns ``(body, init, needs_cytoscape)``:
    the collector-declared catalogue (metadata table + linked graph), an
    edgeless graph's status table (position carries no information without
    edges), or the plain zoomable graph with an equivalent table mode."""
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
        f'placeholder="filter nodes…">{_type_chips(graph)}'
        f'<button class="modeswitch" data-target="{dom_id}" title="图 ⇄ 表切换">表格视图</button>'
        f'<button class="vfit" data-target="{dom_id}" title="重新适配画布">适配</button>'
        f'<span class="hitcount" id="{dom_id}_count" aria-live="polite"></span>'
        f"{_reset_button(dom_id)}"
        "</div>"
        f'<div id="{dom_id}" class="cy"></div>'
        f'<div class="alt-table" hidden>{_status_table_core(graph, dom_id)}</div></div>'
    )
    init = f"initGraph('{dom_id}', {elements}, {opts});\ninitFilterTable('{dom_id}');"
    return body, init, True


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


def _reset_button(dom_id: str) -> str:
    """Hidden until the view has persisted state; clicking clears this view's
    saved filters/viewport and reloads pristine."""
    return f'<button class="vreset" data-target="{dom_id}" hidden>重置视图</button>'


def _row_hint(node: Node) -> str:
    """Inline remediation suffix for a status-table row: the same ``run:`` outlet
    the graph tooltip shows, so the table fallback keeps the action affordance.
    A real button — focusable, click/Enter copies the command."""
    data = node.data or {}
    hint = str(data.get("hint") or "")
    if not hint:
        return ""
    issue = str(data.get("issue") or "")
    tip = _html.escape(f"{issue} · 点击复制" if issue else "点击复制")
    return f' <button class="rhint" type="button" title="{tip}">{_html.escape(hint)}</button>'


_Relations = tuple[dict[str, list[str]], dict[str, list[str]]]


def _status_row(node: Node, relations: _Relations | None = None) -> str:
    label = node.label or str((node.data or {}).get("name") or node.id)
    sval = node.status.value if node.status else ""
    cells = f"<td>{_status_badge(node.status)}</td><td>{_html.escape(label)}{_row_hint(node)}</td>"
    if relations is not None:
        ups, downs = relations
        up = _html.escape(", ".join(ups.get(node.id, [])) or "—")
        down = _html.escape(", ".join(downs.get(node.id, [])) or "—")
        cells += f'<td class="rel">{up}</td><td class="rel">{down}</td>'
    return (
        f'<tr data-node="{_html.escape(node.id)}" data-status="{_html.escape(sval)}">{cells}</tr>'
    )


def _constituency_bar(graph: Graph) -> str:
    counts = Counter(n.status for n in graph.nodes if n.status)
    if not counts:
        return ""
    segments = "".join(
        f'<button class="seg" data-status="{_html.escape(status.value)}" aria-pressed="false" '
        f'style="background:{palette.encoding(status).fill};flex:{count}" '
        f'title="{_html.escape(status.value)}: {count} · 点击只看此状态">{count}</button>'
        for status, count in sorted(counts.items(), key=lambda kv: _status_rank(kv[0]))
    )
    return f'<div class="cbar">{segments}</div>'


# A short table scans fine at a glance; the toolbar earns its row above this.
_TABLE_TOOLBAR_MIN_ROWS = 9


def _status_table_toolbar(graph: Graph, dom_id: str) -> str:
    if len(graph.nodes) < _TABLE_TOOLBAR_MIN_ROWS:
        return ""
    statuses = sorted({n.status for n in graph.nodes if n.status}, key=_status_rank)
    chips = "".join(
        f'<button class="fchip on" data-status="{_html.escape(s.value)}" aria-pressed="true">'
        f"{_html.escape(s.value)}</button>"
        for s in statuses
    )
    return (
        '<div class="toolbar">'
        f'<input class="csearch" id="{dom_id}_q" placeholder="过滤节点…">{chips}'
        f'<span class="hitcount" id="{dom_id}_tcount" aria-live="polite"></span>'
        f"{_reset_button(dom_id)}</div>"
    )


def _status_table_core(graph: Graph, dom_id: str) -> str:
    """Toolbar + constituency bar + anomaly-first table — the shared body of
    the standalone status-table view and a graph view's table mode. A graph
    with edges adds 上游/下游 columns so the table alternative keeps the
    relations the canvas draws instead of dropping them."""
    relations: _Relations | None = None
    if graph.edges:
        label_of = {n.id: (n.label or str((n.data or {}).get("name") or n.id)) for n in graph.nodes}
        ups: dict[str, list[str]] = {}
        downs: dict[str, list[str]] = {}
        for edge in graph.edges:
            downs.setdefault(edge.src, []).append(label_of.get(edge.dst, edge.dst))
            ups.setdefault(edge.dst, []).append(label_of.get(edge.src, edge.src))
        relations = (ups, downs)
    rows = "".join(
        _status_row(node, relations)
        for node in sorted(graph.nodes, key=lambda n: (_status_rank(n.status), n.label or n.id))
    )
    rel_head = "<th>上游</th><th>下游</th>" if relations else ""
    table = (
        f'<table class="stat" id="{dom_id}_tbl"><thead><tr><th>状态</th><th>节点</th>{rel_head}'
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )
    return (
        f"{_status_table_toolbar(graph, dom_id)}{_constituency_bar(graph)}"
        f'<div class="stat-wrap">{table}</div>'
    )


def _status_table_fragment(graph: Graph, dom_id: str) -> tuple[str, str]:
    """An edgeless graph as an anomaly-first table + constituency bar, filtered
    client-side by search / status chips / bar-segment clicks."""
    body = f'<div class="view stat-view">{_status_table_core(graph, dom_id)}</div>'
    return body, f"initFilterTable('{dom_id}');"


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
        f'<button class="fchip on" data-type="{_html.escape(k)}" aria-pressed="true">'
        f"{_html.escape(k)}</button>"
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
        f'{chips}{maint_toggle}<span class="hitcount" id="{dom_id}_count" aria-live="polite">'
        f"</span>{_reset_button(dom_id)}</div>"
    )
    head = (
        "<tr><th>name</th><th>type</th><th>描述</th><th>depends</th><th>tools</th>"
        f'<th>model</th><th class="num">行数</th>'
        f'<th class="num" aria-sort="none"><button class="thsort" id="{dom_id}_tok" '
        f'data-key="est_tokens" title="点击按体量排序">est_tokens</button></th>'
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
            # diameter ∝ √count keeps the AREA proportional to the count —
            # linear diameter growth would visually square the difference
            "symbolSize": min(32, round(9 * math.sqrt(e.count))),
        }
        for e in sorted(view.events, key=lambda e: e.ts)
    ]
    return {
        "title": {"text": view.title or "timeline"},
        "aria": {"enabled": True},
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
        "aria": {"enabled": True},
        "tooltip": {"trigger": "axis"},
        "legend": {"show": len(series_names) > 1},
        "grid": {"containLabel": True},
        "xAxis": {"type": "category", "data": labels, "axisLabel": {"rotate": 30}},
        "yAxis": {"type": "value"},
        "series": series,
    }


def _fmt_num(value: float) -> str:
    return f"{value:g}"


def _metric_card(point: MetricPoint) -> str:
    """flag / index points as text stat cards — a boolean or an ordinal drawn
    as a bar of height 1 or 5 misleads; a card states it."""
    if point.unit == "flag":
        val, cls = ("✓", " ok") if point.value else ("✗", " bad")
    else:
        val, cls = _fmt_num(point.value), ""
    caption = f"{point.series} · {point.label}" if point.series else point.label
    return (
        f'<div class="mcard{cls}"><span class="mcard-v">{val}</span>'
        f'<span class="mcard-l">{_html.escape(caption)}</span></div>'
    )


def _series_option(name: str, points: list[MetricPoint]) -> dict[str, Any]:
    """One small chart per series, on its own axis. ratio / percent series pin
    the domain so the bar height is comparable across snapshots."""
    y: dict[str, Any] = {"type": "value"}
    units = {p.unit for p in points}
    if units == {"ratio"}:
        y["max"] = 1
    elif units == {"percent"}:
        y["max"] = 100
    return {
        "title": {"text": name or "metrics"},
        "aria": {"enabled": True},
        "tooltip": {"trigger": "axis"},
        "grid": {"containLabel": True},
        "xAxis": {"type": "category", "data": [p.label for p in points]},
        "yAxis": y,
        "series": [{"name": name or "value", "type": "bar", "data": [p.value for p in points]}],
    }


def _chart_toolbar(dom_id: str) -> str:
    return (
        f'<div class="toolbar"><button class="modeswitch" data-target="{dom_id}" '
        'title="图 ⇄ 表切换">表格视图</button></div>'
    )


def _metric_summary(view: MetricSeries) -> str:
    if not view.points:
        return ""
    series: list[str] = []
    for p in view.points:
        if p.series not in series:
            series.append(p.series)
    return f'<p class="chart-summary">{len(view.points)} 个指标点 · {len(series)} 组系列</p>'


def _metric_table(view: MetricSeries) -> str:
    has_unit = any(p.unit for p in view.points)
    unit_head = "<th>单位</th>" if has_unit else ""
    rows = "".join(
        f"<tr><td>{_html.escape(p.series)}</td><td>{_html.escape(p.label)}</td>"
        f'<td class="num">{_fmt_num(p.value)}</td>'
        + (f"<td>{_html.escape(p.unit)}</td>" if has_unit else "")
        + "</tr>"
        for p in view.points
    )
    return (
        '<div class="stat-wrap"><table class="stat"><thead><tr><th>系列</th><th>指标</th>'
        f'<th class="num">值</th>{unit_head}</tr></thead><tbody>{rows}</tbody></table></div>'
    )


def _metric_fragment(view: MetricSeries, dom_id: str) -> tuple[str, str, bool]:
    """Unit-aware metric rendering. Returns ``(body, init, needs_echarts)``:
    flag/index points become text cards, the rest one small chart per series —
    a shared value axis across counts, ratios and ordinals misleads. Untagged
    series (no collector units) keep the single shared chart. Every variant
    carries the equivalent data table + text summary."""
    chrome = f"{_chart_toolbar(dom_id)}{_metric_summary(view)}"
    alt = f'<div class="alt-table" hidden>{_metric_table(view)}</div>'
    mode_init = f"initChartMode('{dom_id}');"
    if {p.unit for p in view.points} <= {""}:  # untagged (or empty) series
        body = (
            f'<div class="view">{chrome}'
            f'<div id="{dom_id}_gfx"><div id="{dom_id}" class="chart"></div></div>{alt}</div>'
        )
        init = f"initChart('{dom_id}', {_script_json(_metric_option(view))});\n{mode_init}"
        return body, init, True
    cards: list[str] = []
    chart_groups: dict[str, list[MetricPoint]] = {}
    for p in view.points:
        # point-level routing: a flag/index drawn as a bar misleads regardless
        # of what its series siblings are
        if p.unit in ("flag", "index"):
            cards.append(_metric_card(p))
        else:
            chart_groups.setdefault(p.series, []).append(p)
    charts: list[str] = []
    inits: list[str] = []
    for series, pts in chart_groups.items():
        if len(pts) == 1:  # a one-bar chart carries no comparison — card it
            cards.append(_metric_card(pts[0]))
            continue
        cid = f"{dom_id}_g{len(inits)}"
        charts.append(f'<div id="{cid}" class="chart"></div>')
        inits.append(f"initChart('{cid}', {_script_json(_series_option(series, pts))});")
    card_row = f'<div class="mcards">{"".join(cards)}</div>' if cards else ""
    grid = f'<div class="metric-grid">{"".join(charts)}</div>' if charts else ""
    body = f'<div class="view">{chrome}<div id="{dom_id}_gfx">{card_row}{grid}</div>{alt}</div>'
    return body, "\n".join([*inits, mode_init]), bool(charts)


def _timeline_summary(view: Timeline) -> str:
    if not view.events:
        return ""
    ts = sorted(e.ts for e in view.events)
    lanes = {e.category for e in view.events}
    total = sum(e.count for e in view.events)
    return (
        f'<p class="chart-summary">{total} 个事件 · 跨度 {_html.escape(ts[0][:10])}'
        f" 至 {_html.escape(ts[-1][:10])} · {len(lanes)} 个分类</p>"
    )


def _timeline_table(view: Timeline) -> str:
    rows = "".join(
        f"<tr><td>{_html.escape(e.ts)}</td><td>{_html.escape(e.label)}</td>"
        f'<td>{_html.escape(e.category)}</td><td class="num">{e.count}</td></tr>'
        for e in sorted(view.events, key=lambda e: e.ts)
    )
    return (
        '<div class="stat-wrap"><table class="stat"><thead><tr><th>时间</th><th>事件</th>'
        f'<th>分类</th><th class="num">次数</th></tr></thead><tbody>{rows}</tbody></table></div>'
    )


def _chart_fragment(view: Timeline, dom_id: str) -> tuple[str, str]:
    body = (
        f'<div class="view">{_chart_toolbar(dom_id)}{_timeline_summary(view)}'
        f'<div id="{dom_id}_gfx"><div id="{dom_id}" class="chart"></div></div>'
        f'<div class="alt-table" hidden>{_timeline_table(view)}</div></div>'
    )
    init = (
        f"initChart('{dom_id}', {_script_json(_timeline_option(view))});\n"
        f"initChartMode('{dom_id}');"
    )
    return body, init


def _fragment(view: View, dom_id: str) -> tuple[str, str, str | None]:
    """Return ``(body_html, init_js, lib_name)`` for any IR form. ``lib_name``
    is ``None`` when the fragment needs no library (an edgeless status table,
    a card-only metric view)."""
    if isinstance(view, Graph):
        body, init, needs_cy = _graph_fragment(view, dom_id)
        return body, init, (_CYTOSCAPE if needs_cy else None)
    if isinstance(view, MetricSeries):
        body, init, needs_ec = _metric_fragment(view, dom_id)
        return body, init, (_ECHARTS if needs_ec else None)
    if isinstance(view, Timeline):
        body, init = _chart_fragment(view, dom_id)
        return body, init, _ECHARTS
    raise CataforgeError(f"unrenderable view type: {type(view).__name__}")
