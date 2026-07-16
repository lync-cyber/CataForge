"""KG views: traceability chains, Feature coverage, arch dependency graph.

All three open the `KnowledgeGraph` facade read-only; an uninitialised store
degrades to a `CataforgeError` carrying the facade's own ``kg init`` hint.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, cast

from cataforge.application.viz.collectors._kg import open_kg
from cataforge.core.errors import CataforgeError
from cataforge.core.viz.model import Edge, Graph, Node, Status, View
from cataforge.domain.kg import KnowledgeGraph
from cataforge.domain.kg.trace import TraceChain
from cataforge.runtime.skill.builtins.task_dep_analysis.task_dep_analysis import detect_cycles

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


def _buckets(chain: TraceChain) -> list[tuple[str, list[str]]]:
    return [
        ("requirements", chain.requirements),
        ("acceptance_criteria", chain.acceptance_criteria),
        ("modules", chain.modules),
        ("components", chain.components),
        ("tasks", chain.tasks),
        ("test_cases", chain.test_cases),
        ("review_reports", chain.review_reports),
        ("domain_entities", chain.domain_entities),
    ]


def _merge_chain(
    chain: TraceChain,
    kg: KnowledgeGraph,
    nodes: dict[str, Node],
    edges: set[tuple[str, str, str]],
) -> None:
    buckets = _buckets(chain)
    # each id's chain layer travels as data.type: fold chips and the inspector
    # read the layer from the bucket truth, no id-prefix guessing
    layer = {chain.root_id: "requirements"}
    all_ids = [chain.root_id]
    seen = {chain.root_id}
    for name, ids in buckets:
        for eid in ids:
            layer.setdefault(eid, name)
            if eid not in seen:
                all_ids.append(eid)
                seen.add(eid)
    for eid in all_ids:
        if eid not in nodes:
            entity = kg.query.entity(eid)
            title = entity.get("title", "") if entity else ""
            nodes[eid] = Node(id=eid, label=f"{eid}: {title}", data={"type": layer[eid]})

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
    with open_kg(root) as kg:
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


def _coverage_gap(has_impl: bool, has_test: bool) -> str:
    """Which side of a Feature's chain is missing — the gap a reader must close."""
    if not has_impl and not has_test:
        return "缺实现与测试"
    return "缺测试" if has_impl else "缺实现"


def collect_coverage(root: Path, /, **_opts: Any) -> View:
    """One styled node per Feature: green=impl+test, yellow=partial, red=none.
    Under-covered Features carry a ``data`` bag naming the gap + a drill-in
    command, so a reader lands on the actionable next step, not just a colour."""
    with open_kg(root) as kg:
        rows = kg.trace.bidirectional_coverage()
    nodes = []
    for r in rows:
        if r.has_impl and r.has_test:
            status, data = Status.OK, None
        else:
            status = Status.PARTIAL if (r.has_impl or r.has_test) else Status.MISSING
            data = {
                "issue": _coverage_gap(r.has_impl, r.has_test),
                "hint": f"run: cataforge viz trace {r.entity_id}",
            }
        nodes.append(
            Node(id=r.entity_id, label=f"{r.entity_id}: {r.title or ''}", status=status, data=data)
        )
    return Graph(nodes=tuple(nodes), direction="TD", title="feature coverage")


def collect_arch(root: Path, /, **_opts: Any) -> View:
    """Arch-layer entities with ``depends_on`` dependency edges and ``part_of``
    composition edges; nodes on a ``depends_on`` cycle are marked
    :data:`Status.CYCLE` — the arch layer's dependency graph must be a DAG, so
    a cycle is an anomaly worth a visual warning, not just another edge."""
    labels: dict[str, str] = {}
    edges: list[Edge] = []
    dep_graph: dict[str, list[str]] = defaultdict(list)
    with open_kg(root) as kg:
        entities = kg.query.all_entities(types=_ARCH_TYPES)
        ids = {eid for e in entities if (eid := e.get("entity_id"))}
        for e in entities:
            eid = e.get("entity_id")
            if not eid:
                continue
            labels[eid] = f"{eid}: {e.get('title') or ''}"
            for dep in kg.query.depends_on(eid):
                if dep in ids:
                    edges.append(Edge(eid, dep, label="depends_on"))
                    dep_graph[eid].append(dep)
            for owner in kg.query.part_of(eid):
                if owner in ids:
                    edges.append(Edge(eid, owner, label="part_of"))
    cyclic: set[str] = set()
    for cycle in detect_cycles(dep_graph, set(labels)):
        cyclic.update(cycle)
    nodes = tuple(
        Node(id=eid, label=label, status=Status.CYCLE if eid in cyclic else None)
        for eid, label in labels.items()
    )
    return Graph(nodes=nodes, edges=tuple(edges), direction="LR", title="architecture")
