"""IR → Mermaid text. The single shared Mermaid renderer.

Graph → ``graph`` flowchart; Timeline → ``timeline`` diagram. MetricSeries has
no native Mermaid form (it is a bar/line chart) — it renders via JSON in tier 1
and ECharts in tier 2.
"""

from __future__ import annotations

from cataforge.core.errors import CataforgeError
from cataforge.core.viz.model import Graph, Node, Timeline, View

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


def _render_graph(view: Graph) -> str:
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


def _clean(text: str) -> str:
    """Drop the characters that would break a Mermaid ``timeline`` row, whose
    ``period : event : event`` grammar makes ``:`` and newlines structural."""
    return text.replace(":", "-").replace("\n", " ").strip()


def _render_timeline(view: Timeline) -> str:
    lines = ["timeline", f"    title {view.title or 'timeline'}"]
    grouped: dict[str, list[str]] = {}
    for ev in view.events:
        period = _clean(ev.ts.split("T", 1)[0]) or "n/a"
        grouped.setdefault(period, []).append(_clean(ev.label) or "event")
    if not grouped:
        lines.append("    n/a : no events")
        return "\n".join(lines)
    for period, labels in grouped.items():
        lines.append(f"    {period} : " + " : ".join(labels))
    return "\n".join(lines)


def render(view: View) -> str:
    if isinstance(view, Graph):
        return _render_graph(view)
    if isinstance(view, Timeline):
        return _render_timeline(view)
    raise CataforgeError("Mermaid renderer supports Graph and Timeline views only")
