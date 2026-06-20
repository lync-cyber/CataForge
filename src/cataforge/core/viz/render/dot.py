"""IR → Graphviz DOT text."""

from __future__ import annotations

from cataforge.core.errors import CataforgeError
from cataforge.core.viz.model import Graph, View


def _quote(text: str) -> str:
    return text.replace(chr(34), chr(39))


def render(view: View) -> str:
    if not isinstance(view, Graph):
        raise CataforgeError("DOT renderer supports Graph views only")
    rankdir = "TB" if view.direction in ("TD", "TB") else view.direction
    lines = ["digraph G {", f"  rankdir={rankdir};"]
    for node in view.nodes:
        if node.label is not None:
            lines.append(f'  "{node.id}" [label="{_quote(node.label)}"];')
    for edge in view.edges:
        if edge.label:
            lines.append(f'  "{edge.src}" -> "{edge.dst}" [label="{_quote(edge.label)}"];')
        else:
            lines.append(f'  "{edge.src}" -> "{edge.dst}";')
    lines.append("}")
    return "\n".join(lines)
