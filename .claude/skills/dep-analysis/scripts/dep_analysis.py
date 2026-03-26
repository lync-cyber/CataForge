#!/usr/bin/env python3
"""dep_analysis.py — 任务依赖分析工具

用法: python dep_analysis.py --edges "T-001→T-002,T-002→T-003" [--weights "T-001:S,T-002:M,T-003:L"] [--format json|mermaid]
输出: JSON或Mermaid格式到stdout
返回: exit 0=无环, exit 1=有环
"""

import argparse
import json
import sys
from collections import defaultdict, deque

WEIGHT_MAP = {"S": 1, "M": 2, "L": 3, "XL": 5}


def parse_edges(edges_str: str) -> list[tuple[str, str]]:
    """解析边列表字符串为(from, to)元组列表"""
    edges = []
    for part in edges_str.split(","):
        part = part.strip()
        if not part:
            continue
        # 支持多种箭头格式: →, ->, ─→, ──>
        for sep in ["→", "->", "─→", "──>"]:
            if sep in part:
                nodes = part.split(sep, 1)
                if len(nodes) == 2:
                    edges.append((nodes[0].strip(), nodes[1].strip()))
                break
    return edges


def parse_weights(weights_str: str) -> dict[str, int]:
    """解析权重字符串为{节点: 权重}字典"""
    weights = {}
    if not weights_str:
        return weights
    for part in weights_str.split(","):
        part = part.strip()
        if ":" not in part:
            continue
        node, w = part.rsplit(":", 1)
        node = node.strip()
        w = w.strip().upper()
        weights[node] = WEIGHT_MAP.get(w, 2)  # 默认M=2
    return weights


def detect_cycles(graph: dict[str, list[str]], all_nodes: set[str]) -> list[list[str]]:
    """DFS环检测，返回所有发现的环路径"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in all_nodes}
    parent = {}
    cycles = []

    def dfs(u):
        color[u] = GRAY
        for v in graph.get(u, []):
            if color[v] == GRAY:
                # 发现回边，提取环路径
                cycle = [v]
                node = u
                while node != v:
                    cycle.append(node)
                    node = parent.get(node, v)
                cycle.append(v)
                cycle.reverse()
                cycles.append(cycle)
            elif color[v] == WHITE:
                parent[v] = u
                dfs(v)
        color[u] = BLACK

    for n in sorted(all_nodes):
        if color[n] == WHITE:
            dfs(n)

    return cycles


def topological_sort(graph: dict[str, list[str]], all_nodes: set[str]) -> list[str]:
    """Kahn算法拓扑排序"""
    in_degree = {n: 0 for n in all_nodes}
    for u in graph:
        for v in graph[u]:
            in_degree[v] = in_degree.get(v, 0) + 1

    queue = deque(sorted(n for n in all_nodes if in_degree[n] == 0))
    order = []

    while queue:
        u = queue.popleft()
        order.append(u)
        for v in graph.get(u, []):
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    return order


def critical_path(
    graph: dict[str, list[str]],
    all_nodes: set[str],
    weights: dict[str, int],
    topo_order: list[str],
) -> tuple[list[str], int]:
    """基于权重的最长路径计算"""
    dist = {n: weights.get(n, 2) for n in all_nodes}
    pred = {n: None for n in all_nodes}

    for u in topo_order:
        for v in graph.get(u, []):
            new_dist = dist[u] + weights.get(v, 2)
            if new_dist > dist[v]:
                dist[v] = new_dist
                pred[v] = u

    # 找到距离最大的节点
    end_node = max(all_nodes, key=lambda n: dist[n])
    path = []
    node = end_node
    while node is not None:
        path.append(node)
        node = pred[node]
    path.reverse()

    return path, dist[end_node]


def sprint_groups(graph: dict[str, list[str]], all_nodes: set[str]) -> list[list[str]]:
    """按拓扑层级分组(同层可并行)"""
    in_degree = {n: 0 for n in all_nodes}
    for u in graph:
        for v in graph[u]:
            in_degree[v] = in_degree.get(v, 0) + 1

    groups = []
    remaining = set(all_nodes)

    while remaining:
        # 当前层: 入度为0的节点
        layer = sorted(n for n in remaining if in_degree.get(n, 0) == 0)
        if not layer:
            # 有环导致无法继续，取剩余节点
            groups.append(sorted(remaining))
            break
        groups.append(layer)
        remaining -= set(layer)
        # 更新入度
        for u in layer:
            for v in graph.get(u, []):
                if v in remaining:
                    in_degree[v] -= 1

    return groups


def format_mermaid(edges: list[tuple[str, str]], cp: list[str]) -> str:
    """生成 Mermaid graph LR 格式的依赖图，关键路径节点加粗标注"""
    lines = ["graph LR"]
    cp_set = set(cp)
    # 为关键路径节点添加样式
    for u, v in edges:
        lines.append(f"    {u} --> {v}")
    if cp_set:
        cp_nodes = ",".join(sorted(cp_set))
        lines.append(f"    style {cp_nodes} fill:#f96,stroke:#333,stroke-width:2px")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="任务依赖分析工具")
    parser.add_argument(
        "--edges", required=True, help='边列表: "T-001→T-002,T-002→T-003"'
    )
    parser.add_argument("--weights", default="", help='权重: "T-001:S,T-002:M,T-003:L"')
    parser.add_argument(
        "--format", default="json", choices=["json", "mermaid"],
        help="输出格式: json(默认) 或 mermaid"
    )
    args = parser.parse_args()

    edges = parse_edges(args.edges)
    weights = parse_weights(args.weights)

    # 构建邻接表
    graph: dict[str, list[str]] = defaultdict(list)
    all_nodes: set[str] = set()
    for u, v in edges:
        graph[u].append(v)
        all_nodes.add(u)
        all_nodes.add(v)

    if not all_nodes:
        if args.format == "mermaid":
            print("graph LR\n    empty[无有效边]")
        else:
            print(json.dumps({"error": "无有效边"}, ensure_ascii=False))
        sys.exit(2)

    # 环检测
    cycles = detect_cycles(graph, all_nodes)

    if args.format == "mermaid":
        if cycles:
            # 有环时仍输出图，但标注环节点
            lines = ["graph LR"]
            for u, v in edges:
                lines.append(f"    {u} --> {v}")
            cycle_nodes = set()
            for c in cycles:
                cycle_nodes.update(c)
            if cycle_nodes:
                cn = ",".join(sorted(cycle_nodes))
                lines.append(f"    style {cn} fill:#f00,stroke:#333,stroke-width:2px")
            print("\n".join(lines))
        else:
            cp, _ = critical_path(graph, all_nodes, weights, topological_sort(graph, all_nodes))
            print(format_mermaid(edges, cp))
        sys.exit(1 if cycles else 0)

    # JSON 格式输出 (原有逻辑)
    result = {
        "cycle_detected": len(cycles) > 0,
        "cycles": [c for c in cycles],
    }

    if cycles:
        result["topological_order"] = []
        result["critical_path"] = []
        result["critical_path_weight"] = 0
        result["sprint_groups"] = []
    else:
        topo = topological_sort(graph, all_nodes)
        cp, cp_weight = critical_path(graph, all_nodes, weights, topo)
        groups = sprint_groups(graph, all_nodes)

        result["topological_order"] = topo
        result["critical_path"] = cp
        result["critical_path_weight"] = cp_weight
        result["sprint_groups"] = groups

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1 if cycles else 0)


if __name__ == "__main__":
    main()
