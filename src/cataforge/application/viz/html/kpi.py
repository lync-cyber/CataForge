"""Dashboard KPI strip — the overview series as clickable stat tiles."""

from __future__ import annotations

import html as _html
import re
from pathlib import Path

from cataforge.application.viz.collectors.overview import CURRENT_PREFIX, SELF_CAUSED_LABEL
from cataforge.core.viz.model import MetricSeries, View

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


def read_retro_threshold(root: Path) -> int:
    """The project's retrospective trigger line for the decay tile."""
    from cataforge.runtime.skill.builtins.framework_review._framework_data import (
        read_retro_self_caused_threshold,
    )

    return read_retro_self_caused_threshold(root)
