"""The single extension seam: view-name → collector, format → renderer."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from cataforge.application.viz.collectors import (
    assets,
    decay,
    docs,
    framework,
    overview,
    process,
    tasks,
    trace,
)
from cataforge.application.viz.collectors.base import Collector
from cataforge.core.errors import CataforgeError
from cataforge.core.viz.model import View
from cataforge.core.viz.render import dot, json_, mermaid

COLLECTORS: dict[str, Collector] = {
    "overview": overview.collect,
    "framework": framework.collect,
    "assets": assets.collect,
    "trace": trace.collect_trace,
    "coverage": trace.collect_coverage,
    "arch": trace.collect_arch,
    "docs": docs.collect_docs,
    "tasks": tasks.collect_tasks,
    "phase": process.collect_phase,
    "timeline": process.collect_timeline,
    "decay": decay.collect_decay,
}

RENDERERS: dict[str, Callable[[View], str]] = {
    "mermaid": mermaid.render,
    "dot": dot.render,
    "json": json_.render,
}


_HINT_RE = re.compile(r"`([^`]+)`")


def short_hint(detail: str) -> str:
    """Collapse a collector's error to its actionable command, when it has one.
    Shared by ``viz status`` and the dashboard's degraded KPI tiles, so both
    surfaces guide with the same ``run: <命令>`` line."""
    match = _HINT_RE.search(detail)
    return f"run: {match.group(1)}" if match else detail


def collect_safe(root: Path, name: str) -> tuple[View | None, str | None]:
    """Collect view *name* without raising: returns ``(view, None)`` on success
    or ``(None, message)`` when the collector is unknown or its data source is
    unavailable. Shared by the dashboard (per-panel degradation) and
    ``viz status`` (readiness probe), so the catch-and-degrade lives once."""
    collector = COLLECTORS.get(name)
    if collector is None:
        return None, f"unknown view: {name!r}"
    try:
        return collector(root), None
    except CataforgeError as exc:
        return None, str(exc)
