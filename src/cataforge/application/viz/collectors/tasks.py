"""Task dependency view: dev-plan task DAG with critical-path / cycle styling.

Two data sources, picked by whether ``edges`` is supplied:

* **edges opt** (``T-001→T-002,...``) — the authoring-time path. dev-plan
  mermaid is generated while the plan is still draft and not yet in the KG, so
  the caller passes the edge list it already has (the ``task-dep-analysis``
  annex).
* **KG** (no edges) — reads ``Task`` entities and their ``depends_on`` edges
  from the store, so a finalised plan renders with no manual input.

Either source feeds the same deterministic algorithms in
:mod:`cataforge.runtime.skill.builtins.task_dep_analysis` (topological sort,
critical path, cycle detection) and maps onto the shared Graph IR, so the
rendered mermaid matches what ``task-dep-analysis`` used to print itself.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from cataforge.application.viz import palette
from cataforge.application.viz.collectors._kg import open_kg
from cataforge.core.viz.model import Edge, Graph, Node, View
from cataforge.runtime.skill.builtins.task_dep_analysis.task_dep_analysis import (
    critical_path,
    detect_cycles,
    parse_edges,
    parse_weights,
    topological_sort,
)

_CP_STYLE = palette.RED_CRITICAL_PATH
_CYCLE_STYLE = palette.RED_CYCLE


def _edges_from_kg(root: Path) -> list[tuple[str, str]]:
    """Task DAG edges from the KG: ``dep → task`` for every ``Task.depends_on``
    whose target is also a Task (dep precedes the task that depends on it)."""
    with open_kg(root) as kg:
        ids = {eid for t in kg.query.all_entities(types=["Task"]) if (eid := t.get("entity_id"))}
        edges: list[tuple[str, str]] = []
        for eid in sorted(ids):
            for dep in kg.query.depends_on(eid):
                if dep in ids:
                    edges.append((dep, eid))
    return edges


def collect_tasks(root: Path, /, **opts: Any) -> View:
    """Task DAG graph. Highlights the critical path, or cycle nodes when the
    graph is cyclic. Uses ``edges`` (+ optional ``weights``) when given,
    otherwise reads ``Task.depends_on`` from the KG."""
    edges_str = opts.get("edges", "") or ""
    if edges_str:
        edges = parse_edges(edges_str)
        weights = parse_weights(opts.get("weights", "") or "")
    else:
        edges = _edges_from_kg(root)
        weights = {}

    graph: dict[str, list[str]] = defaultdict(list)
    all_nodes: set[str] = set()
    for u, v in edges:
        graph[u].append(v)
        all_nodes.add(u)
        all_nodes.add(v)

    if not all_nodes:
        return Graph(direction="LR", title="task dependencies")

    cycles = detect_cycles(graph, all_nodes)
    if cycles:
        styled: set[str] = set()
        for cycle in cycles:
            styled.update(cycle)
        style = _CYCLE_STYLE
    else:
        cp, _ = critical_path(graph, all_nodes, weights, topological_sort(graph, all_nodes))
        styled = set(cp)
        style = _CP_STYLE

    return Graph(
        direction="LR",
        edges=tuple(Edge(u, v) for u, v in edges),
        nodes=tuple(Node(n, style=style) for n in styled),
        title="task dependencies",
    )
