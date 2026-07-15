"""Page assembly: single-view pages and the tabbed dashboard.

``render`` produces one standalone file per view; ``render_dashboard``
aggregates every viable view into a tabbed page that shares the two vendored
libraries. Styling comes from ``assets/dashboard.css`` (palette-derived colours
injected as CSS custom properties) and behaviour from the ``assets/dashboard.*
.js`` modules (see ``_DASHBOARD_JS``), all inlined so the output opens offline
with zero external requests.
"""

from __future__ import annotations

import html as _html
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from cataforge.application.viz.html.fragments import (
    _CYTOSCAPE,
    _fragment,
    _read_asset,
    _script_json,
)
from cataforge.application.viz.html.kpi import (
    _kpi_strip,
    _stepper,
    read_retro_threshold,
    snapshot_history,
)
from cataforge.core.viz import palette
from cataforge.core.viz.model import Graph, Status, View, is_empty

_DASHBOARD_CSS = "dashboard.css"
# Behaviour modules concatenated in dependency order: core first (it owns the
# window.__viz namespace every other module reaches through), app last (its
# IIFEs run at parse time, once every function has been declared). Ordering
# between the middle modules is free — they are pure function declarations.
_DASHBOARD_JS: tuple[str, ...] = (
    "dashboard.core.js",
    "dashboard.graph.js",
    "dashboard.catalogue.js",
    "dashboard.table.js",
    "dashboard.app.js",
)

# phase is deliberately absent: progression renders as the stepper strip.
# Labels are Chinese (the page's primary language); each tab's title= keeps
# the CLI view name reachable for `cataforge viz <view>` correspondence.
_DASHBOARD_VIEWS: tuple[tuple[str, str], ...] = (
    ("framework", "编排"),
    ("assets", "资产"),
    ("trace", "追溯"),
    ("coverage", "覆盖"),
    ("arch", "架构"),
    ("docs", "文档"),
    ("tasks", "任务"),
    ("timeline", "时间线"),
    ("decay", "腐化"),
)


def _dashboard_js() -> str:
    """The behaviour modules concatenated in dependency order — the exact JS
    inlined into every rendered page. The single source of truth for what
    ships, so tests assert against this rather than any one module file."""
    return "\n".join(_read_asset(name) for name in _DASHBOARD_JS)


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
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_html.escape(title)}</title>\n<style>{css}</style>\n</head>\n<body>\n"
    )
    scripts = f"<script>\n{_dashboard_js()}\n{chr(10).join(inits)}\n</script>"
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
    header = f"<header><h1>{_html.escape(title)}</h1></header>"
    return _document(title, f"{header}{_legend()}<main>{body}</main>", [init], [lib] if lib else [])


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


def _inline_code(text: str) -> str:
    """Escape *text* and render its backtick spans as ``<code>``."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", _html.escape(text))


def _degraded_inner(name: str, view: View | None, error: str | None, sdlc_na: bool) -> str:
    """The panel body for a failed or empty view: the same actionable guidance
    ``viz status`` gives, instead of a raw error / blank chart. For a project
    that isn't workflow-driven, the SDLC-gated views say so outright instead
    of steering the reader toward a pipeline that doesn't apply."""
    from cataforge.application.viz.registry import short_hint

    if sdlc_na:
        return f'<div class="empty">{_SDLC_NA_HINT}</div>'
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


# SDLC-gated views: their data only exists for a workflow-driven project, so a
# non-driven one gets an explicit N/A instead of kg-init guidance.
_SDLC_VIEWS = frozenset({"trace", "coverage", "arch", "tasks"})
_SDLC_NA_HINT = "SDLC 数据管线对本项目不适用 — 项目未按工作流阶段驱动"

# Three tab clusters: what the project delivers, how its docs/process are
# doing, and what the framework itself is made of. arch / tasks are project
# views (KG arch entities, dev-plan DAG), not framework assets.
_VIEW_GROUPS: dict[str, tuple[str, ...]] = {
    "delivery": ("coverage", "trace", "tasks", "arch"),
    "process": ("docs", "timeline", "decay"),
    "framework": ("framework", "assets"),
}
_TAB_GROUPS: tuple[tuple[str, str], ...] = (
    ("项目交付", "delivery"),
    ("文档与过程", "process"),
    ("框架资产", "framework"),
)

# Views describing the project itself — preferred over framework views when
# picking a data-backed default tab.
_PROJECT_VIEWS = frozenset(_VIEW_GROUPS["delivery"]) | frozenset(_VIEW_GROUPS["process"])


def _default_view(results: _Results, worst_view: str | None) -> str:
    """Which tab opens first: the worst KPI's view, else the first project
    view that actually has data, else the first tab."""
    order = [name for name, _ in _DASHBOARD_VIEWS]
    if worst_view and worst_view in order:
        return worst_view
    for name in order:
        if name in _PROJECT_VIEWS:
            view = results[name][0]
            if view is not None and not is_empty(view):
                return name
    return order[0]


def _dashboard_panel(
    name: str, result: tuple[View | None, str | None], active: bool, sdlc_na: bool
) -> tuple[str, str | None, str | None]:
    """Render one dashboard tab. Returns ``(panel_html, init_js, lib)``;
    ``init_js`` / ``lib`` are ``None`` for empty or failed views."""
    cls = " active" if active else ""
    pid = f"panel-{name}"
    open_ = f'<section id="{pid}" class="panel{cls}" role="tabpanel" aria-labelledby="tab-{name}">'
    view, error = result
    if view is None or is_empty(view):
        inner = _degraded_inner(name, view, error, sdlc_na)
        return (f"{open_}{inner}</section>", None, None)
    body, init, lib = _fragment(view, f"{pid}_v")
    return (f"{open_}{body}</section>", init, lib)


def _grouped_nav(tabs_by_name: dict[str, str]) -> str:
    """Tabs rendered in labelled clusters. Each cluster is its own tablist
    whose only children are tabs (ARIA required-children); the visible group
    label sits outside and names the tablist via aria-labelledby."""
    blocks: list[str] = []
    for title, key in _TAB_GROUPS:
        btns = "".join(tabs_by_name[n] for n in _VIEW_GROUPS[key])
        blocks.append(
            f'<div class="tabgroup"><span class="tglabel" id="tg-{key}">{title}</span>'
            f'<div class="tabrow" role="tablist" aria-labelledby="tg-{key}">{btns}</div></div>'
        )
    return f'<nav class="tabs">{"".join(blocks)}</nav>'


def render_dashboard(root: Path, /, **_opts: Any) -> str:
    from cataforge.application.viz.collectors.process import sdlc_applicable
    from cataforge.application.viz.registry import collect_safe

    results: _Results = {name: collect_safe(root, name) for name, _ in _DASHBOARD_VIEWS}
    panel_ids = {name: f"panel-{name}" for name, _ in _DASHBOARD_VIEWS}
    sdlc_na = not sdlc_applicable(root)
    overview, _ = collect_safe(root, "overview")
    kpis, worst_view = _kpi_strip(
        overview, results, panel_ids, read_retro_threshold(root), snapshot_history(root), sdlc_na
    )
    default_view = _default_view(results, worst_view)

    tabs_by_name: dict[str, str] = {}
    panels: list[str] = []
    panel_inits: dict[str, list[str]] = {}
    libs: list[str] = []
    index: list[dict[str, str]] = []
    for name, label in _DASHBOARD_VIEWS:
        active = name == default_view
        view = results[name][0]
        panel_na = sdlc_na and name in _SDLC_VIEWS and (view is None or is_empty(view))
        panel, init, lib = _dashboard_panel(name, results[name], active, panel_na)
        sel = " sel" if active else ""
        na = " na" if panel_na else ""
        badge = '<span class="nabadge">N/A</span>' if panel_na else ""
        tabs_by_name[name] = (
            f'<button class="tab{sel}{na}" id="tab-{name}" role="tab"'
            f' aria-selected="{"true" if active else "false"}"'
            f' aria-controls="{panel_ids[name]}" tabindex="{"0" if active else "-1"}"'
            f' title="{name}" data-panel="{panel_ids[name]}">{_html.escape(label)}{badge}</button>'
        )
        panels.append(panel)
        if init is not None:
            panel_inits[name] = [init]
        if lib is not None and lib not in libs:
            libs.append(lib)
        if isinstance(view, Graph):
            # the omnibox index: any entity id/label resolves to its panel
            index.extend(
                {
                    "p": panel_ids[name],
                    "id": node.id,
                    "l": node.label or str((node.data or {}).get("name") or node.id),
                }
                for node in view.nodes
            )
    nl = "\n"
    inits = [f"__viz.setIndex({_script_json(index)});"] + [
        f"__viz.register('{panel_ids[name]}', function(){{\n{nl.join(blocks)}\n}});"
        for name, _ in _DASHBOARD_VIEWS
        if (blocks := panel_inits.get(name))
    ]

    header = (
        "<header><h1>CataForge viz dashboard</h1>"
        '<span class="omni-wrap"><input id="omni" role="combobox" aria-expanded="false"'
        ' aria-autocomplete="list" aria-controls="omni_list" aria-label="全局检索实体 id / 名称"'
        ' placeholder="全局检索实体 id / 名称…" autocomplete="off">'
        '<div id="omni_list" role="listbox" aria-label="检索结果" hidden></div>'
        '<span id="omni_status" class="visually-hidden" aria-live="polite"></span>'
        "</span></header>"
    )
    inspector = (
        '<aside id="inspector" role="dialog" aria-label="实体详情" tabindex="-1" hidden></aside>'
    )
    # snapshot provenance: the static file says when its data was frozen; the
    # serve pipeline's auto-reload script rewrites #viewmode to 服务模式
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    footer = (
        f'<footer class="pagefoot">数据截至 {stamp} · <span id="viewmode">快照模式</span></footer>'
    )
    body = (
        header
        + kpis
        + _stepper(root)
        + _legend()
        + _grouped_nav(tabs_by_name)
        + "<main>"
        + "\n".join(panels)
        + "</main>"
        + footer
        + inspector
    )
    return _document("CataForge viz dashboard", body, inits, libs or [_CYTOSCAPE])
