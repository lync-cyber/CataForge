"""The single extension seam: view-name → collector, format → renderer."""

from __future__ import annotations

from collections.abc import Callable

from cataforge.application.viz.collectors import framework
from cataforge.application.viz.collectors.base import Collector
from cataforge.core.viz.model import View
from cataforge.core.viz.render import dot, json_, mermaid

COLLECTORS: dict[str, Collector] = {
    "framework": framework.collect,
}

RENDERERS: dict[str, Callable[[View], str]] = {
    "mermaid": mermaid.render,
    "dot": dot.render,
    "json": json_.render,
}
