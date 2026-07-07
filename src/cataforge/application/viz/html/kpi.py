"""Dashboard KPI strip — the overview series as clickable stat tiles — plus
the SDLC phase stepper that sits under it."""

from __future__ import annotations

import html as _html
import re
from pathlib import Path

from cataforge.application.viz.collectors.overview import SELF_CAUSED_LABEL
from cataforge.core.errors import CataforgeError
from cataforge.core.viz.model import MetricSeries, View

_Results = dict[str, tuple[View | None, str | None]]


# cls → severity rank; the highest-ranked tile decides which tab opens first.
_CLS_RANK = {"na": 0, "ok": 0, "warn": 1, "bad": 2}

# Metric explanations: what the number means, where its threshold comes from,
# what exceeding it implies. Rendered as the tile's hover title.
_DOCS_INFO = "核心文档完成度 — 分母为当前执行模式工作流的文档门禁数；0.5=存在草稿、1=已批准"
_COVERAGE_INFO = (
    "Feature 双向覆盖 — full 需实现与测试均可追溯（来源 KG trace）；"
    "未达 100% 时 Coverage 视图可定位盲区"
)
_LINKS_INFO = (
    "文档链健康 — stale=上游变更未 reconcile；xref=引用不可解析。"
    "xref>0 即红，点击跳转 Docs 视图并聚焦异常"
)
_DECAY_INFO = (
    "self-caused 纠偏累计对 retrospective 触发线"
    "（阈值来源 framework.json#constants.RETRO_TRIGGER_SELF_CAUSED；达线应触发 retro）"
)


def _tile(
    value: str,
    label: str,
    cls: str,
    panel_id: str,
    info: str = "",
    extra: str = "",
    spark: str = "",
) -> tuple[str, int]:
    """A KPI tile plus its severity rank, so the strip can point the default
    tab at the worst signal instead of always opening the first view."""
    title = f' title="{_html.escape(info)}"' if info else ""
    html_ = (
        f'<button class="kpi {cls}"{title}{extra} data-panel="{panel_id}">'
        f'<span class="kpi-v">{_html.escape(value)}</span>'
        f'<span class="kpi-l">{_html.escape(label)}</span>{spark}</button>'
    )
    return html_, _CLS_RANK.get(cls, 0)


def _sparkline(values: list[float]) -> str:
    """A 64×16 polyline of the metric's snapshot history — direction at a
    glance; axes deliberately omitted."""
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    last = len(values) - 1
    pts = " ".join(
        f"{i * 60 / last + 2:.1f},{14 - (v - lo) / span * 12:.1f}" for i, v in enumerate(values)
    )
    return (
        '<svg class="spark" width="64" height="16" viewBox="0 0 64 16" aria-hidden="true">'
        f'<polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>'
    )


_History = list[dict[str, dict[str, float]]]


def snapshot_history(root: Path) -> _History:
    """Snapshot records folded to the overview's groups form, one per record."""
    from cataforge.application.viz.snapshots import read_snapshots

    out: _History = []
    for rec in read_snapshots(root):
        groups: dict[str, dict[str, float]] = {}
        for p in rec.get("points") or []:
            if not isinstance(p, dict):
                continue
            try:
                value = float(p.get("value", 0))
            except (TypeError, ValueError):
                continue
            series, label = p.get("series"), p.get("label")
            if isinstance(series, str) and isinstance(label, str):
                groups.setdefault(series, {})[label] = value
        out.append(groups)
    return out


def _spark_series(history: _History, metric: str) -> list[float]:
    """Extract one tile's value from each snapshot's groups; snapshots missing
    the group are skipped so a late-added metric still trends cleanly."""
    out: list[float] = []
    for groups in history:
        if metric == "docs":
            grp = groups.get("docs")
            if grp:
                out.append(sum(1 for v in grp.values() if v >= 0.5) * 100 / len(grp))
        elif metric == "coverage":
            grp = groups.get("coverage")
            total = sum(grp.values()) if grp else 0
            if grp and total:
                out.append(grp.get("full", 0) * 100 / total)
        elif metric == "links":
            grp = groups.get("links")
            if grp is not None:
                out.append(grp.get("stale", 0) + grp.get("xref_error", 0))
        elif metric == "decay":
            grp = groups.get("decay")
            if grp is not None:
                out.append(grp.get(SELF_CAUSED_LABEL, 0))
    return out


def _missing_hint(results: _Results, name: str, label: str) -> str:
    """Degraded-tile caption: reuse the detail view's own ``run …`` guidance."""
    from cataforge.application.viz.registry import short_hint

    _, error = results.get(name, (None, None))
    if error:
        hinted = short_hint(error)
        if hinted.startswith("run: "):
            return f"{label} · {hinted}"
    return f"{label} · 数据未就绪"


def _docs_tile(
    group: dict[str, float] | None, results: _Results, pid: str, spark: str = ""
) -> tuple[str, int]:
    if not group:
        return _tile("—", _missing_hint(results, "docs", "核心文档"), "na", pid, _DOCS_INFO)
    total = len(group)
    present = sum(1 for v in group.values() if v >= 0.5)
    approved = sum(1 for v in group.values() if v >= 1.0)
    cls = "ok" if present == total else "warn" if present else "bad"
    return _tile(
        f"{present}/{total}", f"核心文档 · {approved} 已批", cls, pid, _DOCS_INFO, spark=spark
    )


def _coverage_tile(
    group: dict[str, float] | None, results: _Results, pid: str, spark: str = ""
) -> tuple[str, int]:
    if not group:
        return _tile(
            "—", _missing_hint(results, "coverage", "Feature 覆盖"), "na", pid, _COVERAGE_INFO
        )
    full, partial, none = (int(group.get(k, 0)) for k in ("full", "partial", "none"))
    total = full + partial + none
    if not total:
        return _tile("—", "Feature 覆盖 · 无 Feature", "na", pid, _COVERAGE_INFO)
    cls = "ok" if full == total else "bad" if full == 0 else "warn"
    pct = round(full * 100 / total)
    gap = total - full  # Features short of the 100% target line
    return _tile(
        f"{pct}%", f"Feature 覆盖 · 缺口 {gap} → 100%", cls, pid, _COVERAGE_INFO, spark=spark
    )


def _links_tile(
    group: dict[str, float] | None, results: _Results, pid: str, spark: str = ""
) -> tuple[str, int]:
    filt = ' data-filter="anomaly"'
    if not group:
        return _tile("—", _missing_hint(results, "docs", "断链 / stale"), "na", pid, _LINKS_INFO)
    stale, xref = int(group.get("stale", 0)), int(group.get("xref_error", 0))
    count = stale + xref
    cls = "ok" if count == 0 else "bad" if xref else "warn"
    return _tile(
        str(count),
        f"断链 / stale · stale {stale} · xref {xref}",
        cls,
        pid,
        _LINKS_INFO,
        filt,
        spark,
    )


_MONTH_RE = re.compile(r"\d{4}-\d{2}")


def _month_over_month(group: dict[str, float]) -> str:
    """↑ / ↓ / → for the two most recent monthly correction counts — direction,
    not just a running total, so a spike or a cooldown is visible at a glance."""
    months = sorted(k for k in group if _MONTH_RE.fullmatch(k))
    if len(months) < 2:
        return "→"
    cur, prev = group[months[-1]], group[months[-2]]
    return "↑" if cur > prev else "↓" if cur < prev else "→"


def _decay_tile(
    group: dict[str, float] | None, pid: str, threshold: int, spark: str = ""
) -> tuple[str, int]:
    """Self-caused corrections against the retrospective trigger line: ``N/阈值``
    plus month-over-month direction. Red once the retro line is reached."""
    g = group or {}
    self_caused = int(g.get(SELF_CAUSED_LABEL, 0))
    cls = "bad" if self_caused >= threshold else "warn" if self_caused else "ok"
    arrow = _month_over_month(g)
    return _tile(
        f"{self_caused}/{threshold}",
        f"self-caused → retro · 环比{arrow}",
        cls,
        pid,
        _DECAY_INFO,
        spark=spark,
    )


def _kpi_strip(
    overview: View | None,
    results: _Results,
    panel_ids: dict[str, str],
    retro_threshold: int,
    history: _History | None = None,
) -> tuple[str, str | None]:
    """Return ``(strip_html, worst_view)``. ``worst_view`` is the view name of
    the highest-severity tile (``None`` when every tile is ok/na), so the caller
    can open the tab that most needs attention."""
    groups: dict[str, dict[str, float]] = {}
    if isinstance(overview, MetricSeries):
        for point in overview.points:
            groups.setdefault(point.series, {})[point.label] = point.value
    hist = history or []
    sparks = {m: _sparkline(_spark_series(hist, m)) for m in ("docs", "coverage", "links", "decay")}
    # (tile, the view its worst state should open); phase lives in the stepper
    tiles = [
        (_docs_tile(groups.get("docs"), results, panel_ids["docs"], sparks["docs"]), "docs"),
        (
            _coverage_tile(
                groups.get("coverage"), results, panel_ids["coverage"], sparks["coverage"]
            ),
            "coverage",
        ),
        (_links_tile(groups.get("links"), results, panel_ids["docs"], sparks["links"]), "docs"),
        (
            _decay_tile(groups.get("decay"), panel_ids["decay"], retro_threshold, sparks["decay"]),
            "decay",
        ),
    ]
    html_ = "".join(tile for (tile, _rank), _view in tiles)
    worst_rank = max((rank for (_tile_html, rank), _view in tiles), default=0)
    worst_view = next(
        (view for (_tile_html, rank), view in tiles if rank == worst_rank and rank > 0), None
    )
    return f'<section class="kpis">{html_}</section>', worst_view


def read_retro_threshold(root: Path) -> int:
    """The project's retrospective trigger line for the decay tile."""
    from cataforge.runtime.skill.builtins.framework_review._framework_data import (
        read_retro_self_caused_threshold,
    )

    return read_retro_self_caused_threshold(root)


def _stepper(root: Path) -> str:
    """The SDLC phase strip under the KPI row: one chip per workflow phase
    (mode-aware count), the current one highlighted, the gate checklist
    expanded when blocked. Phase progression is orientation, not a view —
    it lives here instead of occupying a tab."""
    from cataforge.application.viz.collectors.process import collect_phase_detail

    open_ = '<section class="stepper" role="group" aria-label="SDLC 阶段">'
    try:
        detail = collect_phase_detail(root)
    except CataforgeError:
        return (
            f'{open_}<span class="pchip na">SDLC 阶段 · 数据未就绪'
            "（需项目指令文件 §项目状态）</span></section>"
        )
    if detail.current is None:
        return f'{open_}<span class="pchip na">SDLC 阶段 · 本项目不适用</span></section>'
    idx = detail.sequence.index(detail.current)
    chips: list[str] = []
    for i, phase in enumerate(detail.sequence):
        if i == idx:
            cls = "pchip cur blocked" if detail.blocked else "pchip cur"
        else:
            cls = "pchip done" if i < idx else "pchip todo"
        chips.append(f'<span class="{cls}">{_html.escape(phase)}</span>')
    passed = sum(1 for c in detail.checks if c.ok)
    total = len(detail.checks)
    if detail.blocked:
        items = "".join(
            f'<li class="{"gok" if c.ok else "gbad"}">{"✓" if c.ok else "✗"} '
            f"{_html.escape(c.label)} — {_html.escape(c.detail)}</li>"
            for c in detail.checks
        )
        gate = (
            f'<details class="gates" open><summary>门禁受阻 · {passed}/{total} 通过</summary>'
            f"<ul>{items}</ul></details>"
        )
    else:
        gate = f'<span class="gstat ok">门禁通过 {passed}/{total}</span>'
    arrow = '<span class="parrow">→</span>'
    return f"{open_}{arrow.join(chips)}{gate}</section>"
