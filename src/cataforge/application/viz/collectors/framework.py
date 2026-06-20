"""Framework orchestration view: orchestrator → phase → agent → skill.

Reuses framework-review's discovery helpers (standard-mode workflow routing +
agent skill declarations) rather than re-parsing framework.json / AGENT.md.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from cataforge.core.viz.model import Edge, Graph, Node, View
from cataforge.runtime.skill.builtins.framework_review._discover import (
    discover_agents,
    parse_skills_field,
)
from cataforge.runtime.skill.builtins.framework_review._framework_data import (
    read_workflow_modes,
)

_ROOT_ID = "orchestrator"


def _sid(prefix: str, name: str) -> str:
    return f"{prefix}_{re.sub(r'[^0-9A-Za-z_]', '_', name)}"


def collect(root: Path, /, **_opts: Any) -> View:
    phases = read_workflow_modes(root).get("standard") or []
    agents = discover_agents(root)

    nodes: list[Node] = [Node(id=_ROOT_ID, label=_ROOT_ID)]
    edges: list[Edge] = []
    seen_nodes: set[str] = {_ROOT_ID}
    seen_edges: set[tuple[str, str]] = set()

    def add_node(node: Node) -> None:
        if node.id not in seen_nodes:
            seen_nodes.add(node.id)
            nodes.append(node)

    def add_edge(src: str, dst: str) -> None:
        if (src, dst) not in seen_edges:
            seen_edges.add((src, dst))
            edges.append(Edge(src, dst))

    for phase in phases:
        name = phase.get("phase")
        role = phase.get("role")
        if not isinstance(name, str) or not name:
            continue
        pid = _sid("phase", name)
        add_node(Node(id=pid, label=name))
        add_edge(_ROOT_ID, pid)
        if not isinstance(role, str) or not role:
            continue
        aid = _sid("agent", role)
        add_node(Node(id=aid, label=role))
        add_edge(pid, aid)
        agent_md = agents.get(role)
        if agent_md is None:
            continue
        try:
            content = agent_md.read_text()
        except OSError:
            continue
        for skill in parse_skills_field(content):
            skid = _sid("skill", skill)
            add_node(Node(id=skid, label=skill))
            add_edge(aid, skid)

    return Graph(
        nodes=tuple(nodes),
        edges=tuple(edges),
        direction="TD",
        title="framework orchestration",
    )
