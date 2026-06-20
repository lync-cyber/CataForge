"""Document dependency view: doc-index ``deps`` as a directed graph.

Edges run downstream → upstream (a doc points at what it was written against).
Two failure modes are surfaced visually, reusing the indexer's own validators:

* **stale** — an upstream's ``content_hash`` changed since the downstream
  pinned it (:func:`find_stale_deps`); the downstream node is styled and the
  edge labelled ``stale``.
* **xref-error** — a ``doc_id#§N`` dep that cannot resolve
  (:func:`find_xref_errors`); the edge is labelled ``xref-error`` and a
  dangling target node is styled broken.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cataforge.core.errors import CataforgeError
from cataforge.core.io import read_json
from cataforge.core.viz.model import Edge, Graph, Node, View
from cataforge.domain.docs.indexer import (
    INDEX_FILENAME,
    find_stale_deps,
    find_xref_errors,
)

_STALE_STYLE = "fill:#ff6,stroke:#333"
_BROKEN_STYLE = "fill:#f96,stroke:#900"

# higher = takes precedence when a (doc, upstream) pair has more than one signal
_SEVERITY = {"xref-error": 2, "stale": 1, "depends_on": 0}


def collect_docs(root: Path, /, **_opts: Any) -> View:
    """Doc dependency graph from ``docs/.doc-index.json``; stale / broken deps
    highlighted."""
    index_path = root / "docs" / INDEX_FILENAME
    if not index_path.is_file():
        raise CataforgeError(
            f"doc index not found at {index_path} — run `cataforge context index` first"
        )
    index = read_json(str(index_path))
    documents = index.get("documents") or {}

    root_str = str(root)
    stale_pairs = {(s["doc_id"], s["upstream_id"]) for s in find_stale_deps(root_str)}
    stale_downstream = {doc for doc, _ in stale_pairs}
    xref_bad = {(e["doc_id"], e["ref"]) for e in find_xref_errors(root_str)}

    nodes: dict[str, Node] = {}
    for doc_id, entry in documents.items():
        doc_type = entry.get("doc_type") or ""
        nodes[doc_id] = Node(
            doc_id,
            label=f"{doc_id}: {doc_type}" if doc_type else doc_id,
            style=_STALE_STYLE if doc_id in stale_downstream else None,
        )

    labels: dict[tuple[str, str], str] = {}
    for doc_id, entry in documents.items():
        for dep in entry.get("deps") or []:
            if not isinstance(dep, str):
                continue
            upstream = dep.split("#", 1)[0].strip()
            if not upstream:
                continue
            if (doc_id, upstream) in stale_pairs:
                label = "stale"
            elif (doc_id, dep) in xref_bad:
                label = "xref-error"
            else:
                label = "depends_on"
            key = (doc_id, upstream)
            if key not in labels or _SEVERITY[label] > _SEVERITY[labels[key]]:
                labels[key] = label

    for (_, upstream), label in labels.items():
        if upstream not in nodes:
            nodes[upstream] = Node(
                upstream,
                label=upstream,
                style=_BROKEN_STYLE if label == "xref-error" else None,
            )

    return Graph(
        nodes=tuple(nodes[k] for k in sorted(nodes)),
        edges=tuple(Edge(s, d, label=lbl) for (s, d), lbl in sorted(labels.items())),
        direction="LR",
        title="doc dependencies",
    )
