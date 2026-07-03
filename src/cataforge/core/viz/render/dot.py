"""IR → Graphviz DOT text."""

from __future__ import annotations

from cataforge.core.errors import CataforgeError
from cataforge.core.viz import palette
from cataforge.core.viz.model import Graph, Node, View


def _quote(text: str) -> str:
    return text.replace(chr(34), chr(39))


def _node_attrs(node: Node) -> str:
    label = _quote(palette.marked_label(node.status, node.label or ""))
    attrs = [f'label="{label}"']
    if node.status:
        enc = palette.encoding(node.status)
        attrs.append(f'style=filled, fillcolor="{enc.fill}", color="{enc.stroke}"')
    return ", ".join(attrs)


def render(view: View) -> str:
    if not isinstance(view, Graph):
        raise CataforgeError("DOT renderer supports Graph views only")
    rankdir = "TB" if view.direction in ("TD", "TB") else view.direction
    lines = ["digraph G {", f"  rankdir={rankdir};"]
    for node in view.nodes:
        if node.label is not None:
            lines.append(f'  "{node.id}" [{_node_attrs(node)}];')
    for edge in view.edges:
        if edge.label:
            lines.append(f'  "{edge.src}" -> "{edge.dst}" [label="{_quote(edge.label)}"];')
        else:
            lines.append(f'  "{edge.src}" -> "{edge.dst}";')
    lines.append("}")
    return "\n".join(lines)
