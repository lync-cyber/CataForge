"""Shared helpers for the ``cataforge kg`` subcommand modules.

Hosts the bits that every kg subcommand needs — the ``--project-root``
option, the lazy store loader, CURIE / IRI utilities, and the GraphML
/ mermaid serialisation helpers. Lives in ``cli/kg/`` (not in
``cli/kg_cmd.py``) so the three sub-modules can depend on it without
forming an import cycle through the top-level group definition.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import click

from cataforge.core.paths import find_project_root

# ---- options ------------------------------------------------------------

project_root_option = click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Project root (defaults to walk-up search for .cataforge/).",
)


# ---- store loaders ------------------------------------------------------


def load_store(project_root: Path | None) -> tuple[Any, Path]:
    """Lazy-import RDFLibStore and load it from the discovered project root.

    Returns ``(store, root)`` so callers that derive sibling paths from
    the project root don't have to re-walk for it.
    """
    from cataforge.kg.store import RDFLibStore

    root = Path(project_root) if project_root is not None else find_project_root()
    store = RDFLibStore()
    store.load(root)
    return store, root


def store_to_graph(store: Any) -> Any:
    """Materialise a GraphStore's quads into a plain rdflib Graph.

    Reasoning ignores named-graph context (the inference closure is
    over the asserted set, not per-graph). The result is feedable to
    :func:`cataforge.kg.reasoning.infer` directly.
    """
    from rdflib import Graph

    from cataforge.kg.ontology import bind_namespaces
    from cataforge.kg.store import _object_to_node, _term_to_node

    g = Graph()
    bind_namespaces(g)
    for s, p, o, _ in store:
        g.add((
            _term_to_node(s),
            _term_to_node(p),
            _object_to_node(o),
        ))
    return g


# ---- IRI / CURIE helpers ------------------------------------------------


def expand_or_passthrough(token: str) -> str:
    """Expand a CURIE; on failure return the token unchanged.

    Useful in CLI handlers that accept either a full IRI or a CURIE —
    the user shouldn't have to know which.
    """
    from cataforge.kg.iri import expand_curie

    try:
        return expand_curie(token)
    except ValueError:
        return token


def coerce_set_value(raw: str) -> str | int | float | bool:
    """Best-effort coercion of a ``--set predicate=value`` RHS."""
    if raw.lower() in {"true", "false"}:
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    if (raw.startswith('"') and raw.endswith('"')) or (
        raw.startswith("'") and raw.endswith("'")
    ):
        return raw[1:-1]
    return raw


# ---- shortening / serialisation ----------------------------------------

_PREFIX_TO_SHORT: dict[str, str] = {}


def shorten_triple(s: str, p: str, o: str) -> Any:
    """Replace IRI prefixes with their CURIE short forms where possible."""
    from cataforge.kg.ontology import NAMESPACES
    from cataforge.kg.store import Triple

    global _PREFIX_TO_SHORT
    if not _PREFIX_TO_SHORT:
        _PREFIX_TO_SHORT = {iri: prefix for prefix, iri in NAMESPACES.items()}

    def short(iri: str) -> str:
        for full, prefix in _PREFIX_TO_SHORT.items():
            if iri.startswith(full):
                return f"{prefix}:{iri[len(full):]}"
        return iri

    return Triple(s=short(s), p=short(p), o=short(o))


def to_graphml(store: Any) -> str:
    """Minimal GraphML export — nodes + edges, no attributes."""
    nodes: set[str] = set()
    edges: list[tuple[str, str, str]] = []
    for s, p, o, _ in store:
        nodes.add(s)
        if o.startswith(("http://", "https://")):
            nodes.add(o)
            edges.append((s, p, o))
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <graph id="kg" edgedefault="directed">',
    ]
    for n in sorted(nodes):
        parts.append(f'    <node id="{n}"/>')
    for i, (s, p, o) in enumerate(sorted(edges)):
        parts.append(
            f'    <edge id="e{i}" source="{s}" target="{o}" label="{p}"/>',
        )
    parts.append("  </graph>")
    parts.append("</graphml>")
    return "\n".join(parts) + "\n"


_SAFE_RE = re.compile(r"[^A-Za-z0-9_]")


def safe_token(token: str) -> str:
    """Sanitise an IRI for use as an identifier in mermaid / DOT output."""
    return str(_SAFE_RE.sub("_", token))


def format_coverage(matrix: Any, out_format: str) -> str:
    """Format a :class:`cataforge.kg.query.CoverageMatrix` for CLI output."""
    if out_format == "json":
        return json.dumps({
            "rows": matrix.rows,
            "cols": matrix.cols,
            "cells": [
                {"row": r, "col": c, "covered": True}
                for (r, c) in matrix.cells
            ],
            "gaps": matrix.gaps,
            "coverage_ratio": matrix.coverage_ratio,
        }, ensure_ascii=False, indent=2)
    if out_format == "markdown":
        header = "| row \\ col | " + " | ".join(matrix.cols) + " |"
        sep = "| --- | " + " | ".join("---" for _ in matrix.cols) + " |"
        body = []
        for r in matrix.rows:
            row_cells = [
                "y" if (r, c) in matrix.cells else "-"
                for c in matrix.cols
            ]
            body.append(f"| {r} | " + " | ".join(row_cells) + " |")
        gap_line = (
            f"\n**Gaps**: {', '.join(matrix.gaps)}" if matrix.gaps else ""
        )
        return "\n".join([header, sep, *body]) + gap_line
    if out_format == "mermaid":
        lines = ["graph LR"]
        for r, c in sorted(matrix.cells):
            lines.append(
                f"  {safe_token(r)} --> {safe_token(c)}",
            )
        return "\n".join(lines)
    # table (default)
    lines = []
    for r in matrix.rows:
        for c in matrix.cols:
            mark = "y" if (r, c) in matrix.cells else "-"
            lines.append(f"{r}\t{c}\t{mark}")
    if matrix.gaps:
        lines.append("")
        lines.append("gaps: " + ", ".join(matrix.gaps))
    lines.append(f"coverage: {matrix.coverage_ratio:.2%}")
    return "\n".join(lines)


_DEFAULT_TEMPLATE_DIR = (
    Path(".cataforge") / "skills" / "doc-gen" / "templates" / "standard"
)


def resolve_template_roots(root: Path) -> list[Path]:
    """Project-relative template roots for ``kg render`` / ``kg template-lint``."""
    candidates = [root / _DEFAULT_TEMPLATE_DIR, root / "docs" / "templates"]
    return [p for p in candidates if p.is_dir()]
