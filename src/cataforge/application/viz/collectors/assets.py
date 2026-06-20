"""Asset browser view: every agent and skill, with agent→skill and
skill→skill dependency edges. The HTML renderer adds a search box on top.

Unlike ``framework`` (only standard-mode routed agents), this surfaces the
full catalogue: all discoverable agents plus all skills (builtins + project
overrides), so maintainers can audit dependency hygiene across the board.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from cataforge.core.viz.model import Edge, Graph, Node, View
from cataforge.runtime.agent.manager import AgentManager
from cataforge.runtime.skill.loader import SkillLoader

_AGENT_STYLE = "fill:#cde,stroke:#369"
_SKILL_STYLE = "fill:#efe,stroke:#393"


def _sid(prefix: str, name: str) -> str:
    return f"{prefix}_{re.sub(r'[^0-9A-Za-z_]', '_', name)}"


def collect(root: Path, /, **_opts: Any) -> View:
    agents = AgentManager(root)
    skills = SkillLoader(root).discover()
    skill_ids = {s.id for s in skills}

    nodes: list[Node] = []
    edges: list[Edge] = []
    seen_nodes: set[str] = set()
    seen_edges: set[tuple[str, str]] = set()

    def add_node(nid: str, label: str, style: str) -> None:
        if nid not in seen_nodes:
            seen_nodes.add(nid)
            nodes.append(Node(id=nid, label=label, style=style))

    def add_edge(src: str, dst: str) -> None:
        if (src, dst) not in seen_edges:
            seen_edges.add((src, dst))
            edges.append(Edge(src, dst))

    for aid in agents.list_agents():
        anode = _sid("agent", aid)
        add_node(anode, aid, _AGENT_STYLE)
        for skill in agents.skills_for(aid):
            snode = _sid("skill", skill)
            add_node(snode, skill, _SKILL_STYLE)
            add_edge(anode, snode)

    for meta in skills:
        snode = _sid("skill", meta.id)
        add_node(snode, meta.id, _SKILL_STYLE)
        for dep in meta.depends:
            if dep in skill_ids:
                add_edge(snode, _sid("skill", dep))

    return Graph(
        nodes=tuple(nodes),
        edges=tuple(edges),
        direction="LR",
        title="agent / skill assets",
    )
