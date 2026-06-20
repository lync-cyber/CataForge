"""The single extension seam: view-name → collector, format → renderer."""

from __future__ import annotations

from collections.abc import Callable

from cataforge.application.viz.collectors import (
    assets,
    decay,
    docs,
    framework,
    process,
    tasks,
    trace,
)
from cataforge.application.viz.collectors.base import Collector
from cataforge.core.viz.model import View
from cataforge.core.viz.render import dot, json_, mermaid

COLLECTORS: dict[str, Collector] = {
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
