"""Jinja2 filters used by KG render templates.

All filters canonicalise their output (trim, collapse interior whitespace
runs, normalise line endings) so render-twice idempotency holds even
when the underlying SPARQL result iteration order is unstable. Filters
must be **pure functions** of their input — no I/O, no clock reads — or
the render-twice invariant breaks.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_WHITESPACE_RUN = re.compile(r"[ \t]+")


def _canonicalise(text: str) -> str:
    """Trim, normalise newlines, collapse interior whitespace runs."""
    out = text.replace("\r\n", "\n").replace("\r", "\n")
    out = "\n".join(_WHITESPACE_RUN.sub(" ", line).rstrip() for line in out.split("\n"))
    return out.strip()


def bullet_list(
    rows: Iterable[dict[str, Any]],
    *,
    fmt: str = "{label}",
    indent: int = 0,
) -> str:
    """Render an iterable of row dicts as a markdown bullet list.

    ``fmt`` is a ``str.format``-style template referencing dict keys; rows
    missing any field referenced by ``fmt`` are skipped silently rather
    than raising — KG queries routinely return sparse rows."""
    prefix = " " * indent + "- "
    out: list[str] = []
    for row in rows:
        try:
            out.append(prefix + fmt.format(**row))
        except KeyError:
            continue
    return _canonicalise("\n".join(out))


def table(
    rows: Iterable[dict[str, Any]],
    *,
    columns: list[str] | None = None,
) -> str:
    """Render an iterable of row dicts as a Github-flavoured markdown table.

    Column order: explicit ``columns=`` wins; otherwise the keys of the
    first row in iteration order. Missing cells render as empty string.
    Output is empty when there are no rows (avoids ``| |\\n| --- |``
    half-tables in conditional blocks)."""
    rows_list = list(rows)
    if not rows_list:
        return ""
    cols = columns or list(rows_list[0].keys())
    header = "| " + " | ".join(cols) + " |"
    separator = "| " + " | ".join("---" for _ in cols) + " |"
    body = [
        "| " + " | ".join(str(row.get(c, "")) for c in cols) + " |"
        for row in rows_list
    ]
    return _canonicalise("\n".join([header, separator, *body]))


def mermaid_diagram(
    edges: Iterable[dict[str, Any]],
    *,
    direction: str = "LR",
    src_key: str = "src",
    dst_key: str = "dst",
    label_key: str | None = None,
) -> str:
    """Render an iterable of edge dicts as a mermaid ``graph`` block.

    Node IDs are sanitised (``[^A-Za-z0-9_]`` → ``_``) so SPARQL-returned
    CURIE strings render cleanly without breaking mermaid's parser. The
    edge list is sorted before emission so output is stable across query
    iteration order."""
    pairs: list[tuple[str, str, str | None]] = []
    for e in edges:
        src = str(e.get(src_key, "")).strip()
        dst = str(e.get(dst_key, "")).strip()
        if not src or not dst:
            continue
        lbl = None
        if label_key is not None:
            raw_lbl = e.get(label_key)
            lbl = str(raw_lbl) if raw_lbl is not None else None
        pairs.append((src, dst, lbl))

    pairs.sort()
    if not pairs:
        return f"graph {direction}"

    lines = [f"graph {direction}"]
    for src, dst, lbl in pairs:
        edge = "-->" if lbl is None else f"-- {lbl} -->"
        lines.append(f"  {_safe_node_id(src)} {edge} {_safe_node_id(dst)}")
    return _canonicalise("\n".join(lines))


_NODE_SAFE_RE = re.compile(r"[^A-Za-z0-9_]")


def _safe_node_id(token: str) -> str:
    return _NODE_SAFE_RE.sub("_", token)


def link_to(
    iri: str,
    *,
    label: str | None = None,
    doc_root: str = "docs",
) -> str:
    """Render an IRI as a markdown link.

    The link target is derived from the IRI's local part using a simple
    convention: ``cfa:<doc-slug>/<display-id>`` → ``<doc_root>/<doc-slug>.md#<display-id>``.
    Plain IRIs without a local hierarchy fall back to bare-text rendering."""
    local = iri.split(":", 1)[1] if ":" in iri else iri
    if "/" not in local:
        return label or iri
    doc_slug, display_id = local.rsplit("/", 1)
    visible = label or display_id
    return f"[{visible}]({doc_root}/{doc_slug}.md#{display_id})"
