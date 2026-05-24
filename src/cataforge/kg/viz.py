"""KG visualisation — mermaid / DOT / SVG renderers (design §5.1 E2).

Each renderer takes a :class:`ViewSpec` describing the slice to draw
(optional class filter, optional anchor node + traversal depth) and
returns a string (mermaid / DOT) or bytes (SVG). SVG is produced by
shelling out to the ``dot`` binary; if it isn't on PATH the caller is
expected to fall back to DOT text — the CLI does this automatically."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from cataforge.kg.ontology import NAMESPACES
from cataforge.kg.query import _expand_curie, _shorten_iri
from cataforge.kg.store import GraphStore


@dataclass(frozen=True)
class ViewSpec:
    """Slice of the KG to visualise.

    All three fields are optional:

    * ``scope_class``: include only instances of this CURIE class (and
      edges where both endpoints fall inside the slice).
    * ``root_node``: anchor the slice at one node and traverse outward
      ``depth`` hops; mutually exclusive with ``scope_class``.
    * ``depth``: only meaningful with ``root_node``."""

    scope_class: str | None = None
    root_node: str | None = None
    depth: int = 2


# ---------- common pipeline ----------

def _collect_edges(
    store: GraphStore, spec: ViewSpec,
) -> tuple[set[str], list[tuple[str, str, str]]]:
    """Return (nodes, edges) for the requested view.

    Edges are returned as ``(src_short, predicate_short, dst_short)``
    tuples. Self-loops and literal objects are excluded — those would
    add noise without helping the reviewer see structure."""
    nodes: set[str] = set()
    edges: list[tuple[str, str, str]] = []

    if spec.root_node is not None:
        rows = _rows_from_root(store, spec.root_node, spec.depth)
    elif spec.scope_class is not None:
        rows = _rows_from_class(store, spec.scope_class)
    else:
        rows = _rows_full(store)

    for row in rows:
        src = _shorten_iri(row["src"])
        dst = _shorten_iri(row["dst"])
        pred = _shorten_iri(row["predicate"])
        if src == dst:
            continue
        nodes.add(src)
        nodes.add(dst)
        edges.append((src, pred, dst))
    return nodes, edges


def _rows_full(store: GraphStore) -> list[dict[str, str]]:
    return store.query(
        "SELECT ?src ?predicate ?dst WHERE {\n"
        "  ?src ?predicate ?dst .\n"
        "  FILTER (isIRI(?dst))\n"
        "} ORDER BY ?src ?predicate ?dst",
    )


def _rows_from_class(store: GraphStore, class_curie: str) -> list[dict[str, str]]:
    prefix_header = "\n".join(
        f"PREFIX {p}: <{iri}>" for p, iri in NAMESPACES.items()
    )
    return store.query(
        prefix_header + "\n"
        + "SELECT ?src ?predicate ?dst WHERE {\n"
        + f"  ?src a {class_curie} ;\n"
        + "       ?predicate ?dst .\n"
        + "  FILTER (isIRI(?dst))\n"
        + "} ORDER BY ?src ?predicate ?dst",
    )


def _rows_from_root(
    store: GraphStore, root: str, depth: int,
) -> list[dict[str, str]]:
    """Walk ``depth`` hops outward from ``root`` along any IRI predicate."""
    full = _expand_curie(root)
    rows: list[dict[str, str]] = []
    frontier = {full}
    seen: set[str] = set()
    for _ in range(max(depth, 0) + 1):
        next_frontier: set[str] = set()
        for node in frontier - seen:
            seen.add(node)
            hits = store.query(
                "SELECT ?predicate ?dst WHERE {\n"
                f"  <{node}> ?predicate ?dst .\n"
                "  FILTER (isIRI(?dst))\n"
                "}",
            )
            for h in hits:
                rows.append({"src": node, **h})
                next_frontier.add(h["dst"])
        frontier = next_frontier
    return rows


# ---------- mermaid ----------

def render_mermaid(store: GraphStore, spec: ViewSpec) -> str:
    """Render as a mermaid ``graph LR`` snippet."""
    nodes, edges = _collect_edges(store, spec)
    parts = ["graph LR"]
    for n in sorted(nodes):
        parts.append(f"    {_mermaid_id(n)}[{_mermaid_label(n)}]")
    for src, pred, dst in sorted(edges):
        parts.append(
            f"    {_mermaid_id(src)} -->|{_mermaid_label(pred)}| "
            f"{_mermaid_id(dst)}",
        )
    return "\n".join(parts) + "\n"


def _mermaid_id(curie: str) -> str:
    """Mermaid node IDs are restricted to alnum + underscore."""
    out = []
    for ch in curie:
        out.append(ch if ch.isalnum() else "_")
    return "n_" + "".join(out)


def _mermaid_label(curie: str) -> str:
    """Mermaid labels are wrapped in [] and must not contain []."""
    return curie.replace("[", "(").replace("]", ")").replace('"', "'")


# ---------- DOT ----------

def render_dot(store: GraphStore, spec: ViewSpec) -> str:
    """Render as a Graphviz DOT digraph."""
    nodes, edges = _collect_edges(store, spec)
    parts = ["digraph kg {", '  rankdir="LR";']
    for n in sorted(nodes):
        parts.append(f'  "{n}" [label="{n}"];')
    for src, pred, dst in sorted(edges):
        parts.append(f'  "{src}" -> "{dst}" [label="{pred}"];')
    parts.append("}")
    return "\n".join(parts) + "\n"


# ---------- SVG (via dot) ----------

def render_svg(store: GraphStore, spec: ViewSpec) -> bytes:
    """Pipe the DOT output through ``dot -Tsvg`` to produce an SVG.

    Raises :class:`FileNotFoundError` when the ``dot`` binary is not on
    PATH — the CLI surface catches this and falls back to DOT text."""
    dot_text = render_dot(store, spec)
    try:
        proc = subprocess.run(
            ["dot", "-Tsvg"],
            input=dot_text.encode("utf-8"),
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        raise
    return proc.stdout
