"""KG views: traceability chains, Feature coverage, arch dependency graph.

All three open the `KnowledgeGraph` facade read-only; an uninitialised store
degrades to a `CataforgeError` carrying the facade's own ``kg init`` hint.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from cataforge.core.errors import CataforgeError
from cataforge.core.paths import KG_STORE_REL
from cataforge.core.viz.model import Edge, Graph, Node, View
from cataforge.domain.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraph
from cataforge.domain.kg.trace import TraceChain

# coverage status → Mermaid style body
_FULL_STYLE = "fill:#9f6,stroke:#333"
_PARTIAL_STYLE = "fill:#ff6,stroke:#333"
_NONE_STYLE = "fill:#f96,stroke:#333"

# (src_layer, dst_layer, relation) — trace-chain edge topology, shared with the
# table/json analysis outputs that `kg trace` still serves.
_CHAIN_EDGES = [
    ("requirements", "modules", "implements"),
    ("requirements", "components", "implements"),
    ("modules", "tasks", "decomposes"),
    ("acceptance_criteria", "test_cases", "verifies"),
    ("requirements", "acceptance_criteria", "validates"),
]

_ARCH_TYPES = ["Module", "Component", "API", "DataModel"]


@contextmanager
def _open_kg(root: Path) -> Generator[KnowledgeGraph, None, None]:
    config = KGConfig(store_backend="oxigraph", db_path=root / KG_STORE_REL)
    try:
        with KnowledgeGraph.connect(config, read_only=True) as kg:
            yield kg
    except KGStoreNotInitializedError as exc:
        raise CataforgeError(str(exc)) from exc


def _buckets(chain: TraceChain) -> list[tuple[str, list[str]]]:
    return [
        ("requirements", chain.requirements),
        ("acceptance_criteria", chain.acceptance_criteria),
        ("modules", chain.modules),
        ("components", chain.components),
        ("tasks", chain.tasks),
        ("test_cases", chain.test_cases),
        ("review_reports", chain.review_reports),
    ]


def _merge_chain(
    chain: TraceChain,
    kg: KnowledgeGraph,
    nodes: dict[str, Node],
    edges: set[tuple[str, str, str]],
) -> None:
    buckets = _buckets(chain)
    all_ids = [chain.root_id]
    seen = {chain.root_id}
    for _, ids in buckets:
        for eid in ids:
            if eid not in seen:
                all_ids.append(eid)
                seen.add(eid)
    for eid in all_ids:
        if eid not in nodes:
            entity = kg.query.entity(eid)
            title = entity.get("title", "") if entity else ""
            nodes[eid] = Node(id=eid, label=f"{eid}: {title}")

    bucket_map = {name: ids for name, ids in buckets}
    for src_layer, dst_layer, rel in _CHAIN_EDGES:
        for s in bucket_map.get(src_layer, []):
            for d in bucket_map.get(dst_layer, []):
                edges.add((s, d, rel))

    downstream = [eid for eid in all_ids if eid != chain.root_id]
    if downstream and not any(
        bucket_map.get(src) and bucket_map.get(dst) for src, dst, _ in _CHAIN_EDGES
    ):
        for d in downstream:
            edges.add((chain.root_id, d, ""))


def collect_trace(root: Path, /, **opts: Any) -> View:
    """Trace graph rooted at ``entity_id``; omit it to aggregate all Features."""
    entity_id = opts.get("entity_id")
    direction = opts.get("direction", "downstream")
    nodes: dict[str, Node] = {}
    edges: set[tuple[str, str, str]] = set()
    with _open_kg(root) as kg:
        if entity_id:
            if not kg.query.exists(entity_id):
                raise CataforgeError(f"Entity not found: {entity_id}")
            roots = [entity_id]
        else:
            roots = [
                eid for e in kg.query.all_entities(types=["Feature"]) if (eid := e.get("entity_id"))
            ]
        for rid in roots:
            chain = kg.trace.from_requirement(rid, direction=cast("Any", direction))
            _merge_chain(chain, kg, nodes, edges)
    return Graph(
        nodes=tuple(nodes.values()),
        edges=tuple(Edge(s, d, label=lbl or None) for s, d, lbl in sorted(edges)),
        direction="TD",
        title="traceability",
    )


def collect_coverage(root: Path, /, **_opts: Any) -> View:
    """One styled node per Feature: green=impl+test, yellow=partial, red=none."""
    with _open_kg(root) as kg:
        rows = kg.trace.bidirectional_coverage()
    nodes = []
    for r in rows:
        if r.has_impl and r.has_test:
            style = _FULL_STYLE
        elif r.has_impl or r.has_test:
            style = _PARTIAL_STYLE
        else:
            style = _NONE_STYLE
        nodes.append(Node(id=r.feature_id, label=f"{r.feature_id}: {r.title or ''}", style=style))
    return Graph(nodes=tuple(nodes), direction="TD", title="feature coverage")


def collect_arch(root: Path, /, **_opts: Any) -> View:
    """Arch-layer entities with intra-layer ``depends_on`` edges."""
    nodes: list[Node] = []
    edges: list[Edge] = []
    with _open_kg(root) as kg:
        entities = kg.query.all_entities(types=_ARCH_TYPES)
        ids = {eid for e in entities if (eid := e.get("entity_id"))}
        for e in entities:
            eid = e.get("entity_id")
            if not eid:
                continue
            nodes.append(Node(id=eid, label=f"{eid}: {e.get('title') or ''}"))
            for dep in kg.query.depends_on(eid):
                if dep in ids:
                    edges.append(Edge(eid, dep, label="depends_on"))
    return Graph(nodes=tuple(nodes), edges=tuple(edges), direction="LR", title="architecture")
