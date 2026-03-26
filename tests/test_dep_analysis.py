"""dep_analysis.py 图算法测试"""

import os
import sys
from collections import defaultdict


# dep_analysis.py 位于 skills 子目录
_dep_dir = os.path.join(
    os.path.dirname(__file__), "..", ".claude", "skills", "dep-analysis", "scripts"
)
sys.path.insert(0, _dep_dir)
from dep_analysis import (
    critical_path,
    detect_cycles,
    format_mermaid,
    parse_edges,
    parse_weights,
    sprint_groups,
    topological_sort,
)


def build_graph(edges):
    """从边列表构建邻接表和节点集"""
    graph = defaultdict(list)
    nodes = set()
    for u, v in edges:
        graph[u].append(v)
        nodes.add(u)
        nodes.add(v)
    return dict(graph), nodes


# ── parse_edges ──────────────────────────────────────────────────────────


class TestParseEdges:
    def test_arrow(self):
        assert parse_edges("A→B") == [("A", "B")]

    def test_dash_arrow(self):
        assert parse_edges("A->B") == [("A", "B")]

    def test_multiple(self):
        result = parse_edges("A→B,B→C,C→D")
        assert len(result) == 3
        assert ("A", "B") in result
        assert ("C", "D") in result

    def test_whitespace(self):
        result = parse_edges(" A → B , B → C ")
        assert result == [("A", "B"), ("B", "C")]

    def test_empty(self):
        assert parse_edges("") == []

    def test_task_ids(self):
        result = parse_edges("T-001→T-002,T-002→T-003")
        assert result == [("T-001", "T-002"), ("T-002", "T-003")]


# ── parse_weights ────────────────────────────────────────────────────────


class TestParseWeights:
    def test_normal(self):
        result = parse_weights("T-001:S,T-002:M,T-003:L")
        assert result == {"T-001": 1, "T-002": 2, "T-003": 3}

    def test_xl(self):
        result = parse_weights("T-001:XL")
        assert result["T-001"] == 5

    def test_case_insensitive(self):
        result = parse_weights("A:s,B:m")
        assert result == {"A": 1, "B": 2}

    def test_empty(self):
        assert parse_weights("") == {}

    def test_unknown_defaults_m(self):
        result = parse_weights("A:UNKNOWN")
        assert result["A"] == 2  # 默认 M=2


# ── detect_cycles ────────────────────────────────────────────────────────


class TestDetectCycles:
    def test_no_cycle(self):
        graph, nodes = build_graph([("A", "B"), ("B", "C")])
        cycles = detect_cycles(graph, nodes)
        assert len(cycles) == 0

    def test_simple_cycle(self):
        graph, nodes = build_graph([("A", "B"), ("B", "C"), ("C", "A")])
        cycles = detect_cycles(graph, nodes)
        assert len(cycles) >= 1

    def test_self_loop(self):
        graph, nodes = build_graph([("A", "A")])
        cycles = detect_cycles(graph, nodes)
        assert len(cycles) >= 1

    def test_diamond_no_cycle(self):
        graph, nodes = build_graph([("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")])
        cycles = detect_cycles(graph, nodes)
        assert len(cycles) == 0


# ── topological_sort ─────────────────────────────────────────────────────


class TestTopologicalSort:
    def test_linear(self):
        graph, nodes = build_graph([("A", "B"), ("B", "C")])
        order = topological_sort(graph, nodes)
        assert order.index("A") < order.index("B") < order.index("C")

    def test_diamond(self):
        graph, nodes = build_graph([("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")])
        order = topological_sort(graph, nodes)
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")

    def test_single_node(self):
        order = topological_sort({}, {"A"})
        assert order == ["A"]


# ── critical_path ────────────────────────────────────────────────────────


class TestCriticalPath:
    def test_linear(self):
        graph, nodes = build_graph([("A", "B"), ("B", "C")])
        weights = {"A": 1, "B": 2, "C": 3}
        topo = topological_sort(graph, nodes)
        path, total = critical_path(graph, nodes, weights, topo)
        assert path == ["A", "B", "C"]
        assert total == 6  # 1+2+3

    def test_parallel_branches(self):
        graph, nodes = build_graph([("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")])
        weights = {"A": 1, "B": 10, "C": 1, "D": 1}
        topo = topological_sort(graph, nodes)
        path, total = critical_path(graph, nodes, weights, topo)
        assert "B" in path  # B 权重更大，应在关键路径
        assert total == 12  # A(1) + B(10) + D(1)


# ── sprint_groups ────────────────────────────────────────────────────────


class TestSprintGroups:
    def test_linear(self):
        graph, nodes = build_graph([("A", "B"), ("B", "C")])
        groups = sprint_groups(graph, nodes)
        assert groups == [["A"], ["B"], ["C"]]

    def test_parallel(self):
        graph, nodes = build_graph([("A", "B"), ("A", "C")])
        groups = sprint_groups(graph, nodes)
        assert groups[0] == ["A"]
        assert set(groups[1]) == {"B", "C"}

    def test_independent(self):
        groups = sprint_groups({}, {"A", "B", "C"})
        assert len(groups) == 1
        assert set(groups[0]) == {"A", "B", "C"}


# ── format_mermaid ───────────────────────────────────────────────────────


class TestFormatMermaid:
    def test_basic(self):
        result = format_mermaid([("A", "B"), ("B", "C")], ["A", "B"])
        assert "graph LR" in result
        assert "A --> B" in result
        assert "style" in result
