"""Asset catalogue view: every agent, skill and rules file, with agent→skill
and skill→skill dependency edges.

Unlike ``framework`` (only standard-mode routed agents), this surfaces the
full catalogue: all discoverable agents plus all skills (builtins + project
overrides) plus the shared rules files, so maintainers can audit dependency
hygiene and prompt-asset volume across the board.

Each node carries a ``data`` bag (description / depends / tools / volume /
source path) that the HTML renderer projects as a searchable catalogue table.
Text renderers ignore it, so the Mermaid/DOT topology is unchanged; rules
files take part in no dependency edge, so they ride as implicit nodes
(``label=None``) visible only to the JSON/HTML consumers.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from cataforge.core.paths import ProjectPaths
from cataforge.core.viz.model import Edge, Graph, Node, Status, View
from cataforge.domain.docs.indexer import estimate_tokens
from cataforge.runtime.agent.manager import AgentManager
from cataforge.runtime.skill.loader import SkillLoader, SkillMeta
from cataforge.utils.frontmatter import split_yaml_frontmatter


def _sid(prefix: str, name: str) -> str:
    return f"{prefix}_{re.sub(r'[^0-9A-Za-z_]', '_', name)}"


def _join(value: object) -> str:
    """Normalise a frontmatter list / comma-string field for display."""
    if isinstance(value, list):
        return ", ".join(s for v in value if (s := str(v).strip()))
    return str(value).strip() if value else ""


def _volume(path: Path | None, root: Path) -> dict[str, object]:
    """``lines`` / ``est_tokens`` / repo-relative ``path`` for a source file.
    A missing or unreadable file (e.g. a script-only builtin skill, or a
    stray non-UTF-8 file) keeps the keys with ``None`` so consumers render a
    uniform placeholder — one bad file must not sink the whole view."""
    if path is None or not path.is_file():
        return {"lines": None, "est_tokens": None, "path": ""}
    try:
        rel = str(path.relative_to(root))
    except ValueError:  # outside the project tree (package builtin / user layer)
        rel = str(path)
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return {"lines": None, "est_tokens": None, "path": rel}
    return {"lines": len(text.splitlines()), "est_tokens": estimate_tokens(text), "path": rel}


def _agent_data(
    root: Path, agent_id: str, content: str | None, skills: list[str]
) -> dict[str, object]:
    fm = split_yaml_frontmatter(content)[0] if content else None
    fm = fm or {}
    agent_md = ProjectPaths(root).agents_dir / agent_id / "AGENT.md"
    return {
        "type": "agent",
        "name": agent_id,
        "description": str(fm.get("description", "")),
        "depends": _join(skills),
        "tools": _join(fm.get("tools")),
        "model": str(fm.get("model", "")),
        "maintainer_only": False,
        **_volume(agent_md if agent_md.is_file() else None, root),
    }


def _skill_data(meta: SkillMeta, root: Path) -> dict[str, object]:
    return {
        "type": "skill",
        "name": meta.id,
        "description": meta.description,
        "depends": _join(meta.depends),
        "tools": _join(meta.suggested_tools),
        "model": "",
        "maintainer_only": meta.maintainer_only,
        **_volume(meta.path, root),
    }


def _rules_data(rules_md: Path, root: Path) -> dict[str, object]:
    return {
        "type": "rules",
        "name": rules_md.stem,
        "description": "",
        "depends": "",
        "tools": "",
        "model": "",
        "maintainer_only": False,
        **_volume(rules_md, root),
    }


def collect(root: Path, /, **_opts: Any) -> View:
    agents = AgentManager(root)
    skills = SkillLoader(root).discover()
    skill_ids = {s.id for s in skills}
    skill_meta = {s.id: s for s in skills}

    nodes: list[Node] = []
    edges: list[Edge] = []
    seen_nodes: set[str] = set()
    seen_edges: set[tuple[str, str]] = set()

    def add_node(node: Node) -> None:
        if node.id not in seen_nodes:
            seen_nodes.add(node.id)
            nodes.append(node)

    def add_edge(src: str, dst: str) -> None:
        if (src, dst) not in seen_edges:
            seen_edges.add((src, dst))
            edges.append(Edge(src, dst))

    def skill_node(skill_id: str) -> Node:
        meta = skill_meta.get(skill_id)
        data = _skill_data(meta, root) if meta else None
        return Node(id=_sid("skill", skill_id), label=skill_id, status=Status.SKILL, data=data)

    for aid in agents.list_agents():
        anode = _sid("agent", aid)
        agent_skills = agents.skills_for(aid)
        add_node(
            Node(
                id=anode,
                label=aid,
                status=Status.AGENT,
                data=_agent_data(root, aid, agents.get_agent_content(aid), agent_skills),
            )
        )
        for skill in agent_skills:
            add_node(skill_node(skill))
            add_edge(anode, _sid("skill", skill))

    for meta in skills:
        add_node(skill_node(meta.id))
        for dep in meta.depends:
            if dep in skill_ids:
                add_edge(_sid("skill", meta.id), _sid("skill", dep))

    # Rules take part in no dependency edge: implicit nodes (no label/style)
    # keep the Mermaid/DOT output unchanged while the catalogue lists them.
    rules_dir = ProjectPaths(root).rules_dir
    if rules_dir.is_dir():
        for rules_md in sorted(rules_dir.glob("*.md")):
            add_node(Node(id=_sid("rules", rules_md.stem), data=_rules_data(rules_md, root)))

    return Graph(
        nodes=tuple(nodes),
        edges=tuple(edges),
        direction="LR",
        title="agent / skill assets",
    )
