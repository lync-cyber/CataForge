"""IR → Mermaid flowchart text. The single shared Mermaid renderer."""

from __future__ import annotations

from cataforge.core.errors import CataforgeError
from cataforge.core.viz.model import Graph, Node, View

# Characters that make a node label ambiguous to Mermaid's parser; a label
# containing any of them is wrapped in quotes. CJK and plain identifiers pass
# through unquoted, matching hand-written Mermaid.
_QUOTE_CHARS = frozenset(' :"[](){}|<>#;')


def _needs_quote(label: str) -> bool:
    return label == "" or any(c in _QUOTE_CHARS for c in label)


def _node_decl(node: Node) -> str:
    label = node.label or ""
    if _needs_quote(label):
        return f'{node.id}["{label.replace(chr(34), chr(39))}"]'
    return f"{node.id}[{label}]"


def _style_lines(nodes: tuple[Node, ...]) -> list[str]:
    groups: dict[str, list[str]] = {}
    for node in nodes:
        if node.style:
            groups.setdefault(node.style, []).append(node.id)
    return [f"    style {','.join(sorted(set(ids)))} {css}" for css, ids in groups.items()]


def render(view: View) -> str:
    if not isinstance(view, Graph):
        raise CataforgeError("Mermaid renderer supports Graph views only")
    lines = [f"graph {view.direction}"]
    for node in view.nodes:
        if node.label is not None:
            lines.append(f"    {_node_decl(node)}")
    for edge in view.edges:
        if edge.label:
            lines.append(f"    {edge.src} -->|{edge.label}| {edge.dst}")
        else:
            lines.append(f"    {edge.src} --> {edge.dst}")
    lines.extend(_style_lines(view.nodes))
    return "\n".join(lines)
