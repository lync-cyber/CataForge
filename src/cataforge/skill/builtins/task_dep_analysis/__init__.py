"""Built-in task-dep-analysis skill (renamed from dep-analysis in v0.1.15).

``CHECKS_MANIFEST`` declares the deterministic graph algorithms exposed
by ``task_dep_analysis.py`` so that ``framework-review`` can verify the
SKILL.md prose stays aligned with the actual capability surface.

Scope is **task DAG** only (dev-plan §1 Sprint task table). For code
module dependency graphs (pydeps / madge / go mod graph), see
``code-review scan --focus coupling``.
"""

from __future__ import annotations

CHECKS_MANIFEST: tuple[dict[str, str], ...] = (
    {
        "id": "cycle_detect",
        "title": "DFS 环检测 (输出循环路径或 PASS)",
        "severity": "fail",
    },
    {
        "id": "topological_sort",
        "title": "Kahn 算法拓扑排序 (输出有效执行顺序)",
        "severity": "info",
    },
    {
        "id": "critical_path",
        "title": "关键路径 (基于复杂度权重 S=1/M=2/L=3/XL=5)",
        "severity": "info",
    },
    {
        "id": "sprint_grouping",
        "title": "按拓扑层级和并行度的 Sprint 分组建议",
        "severity": "info",
    },
)
