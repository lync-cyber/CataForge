"""Built-in framework-review skill.

Audits CataForge meta-assets (.cataforge/agents, .cataforge/skills,
.cataforge/rules) for content quality, cross-reference integrity,
SKILL.md ↔ CHECKS_MANIFEST drift, hard-coded constant drift, and
workflow phase × agent × skill coverage. Counterpart to
``platform-audit`` (which audits external IDE profiles).
"""

from __future__ import annotations

CHECKS_MANIFEST: tuple[dict[str, str], ...] = (
    {
        "id": "B1_required_sections",
        "title": (
            "AGENT.md / SKILL.md 必填段"
            "（能力边界 / 输入规范 / 输出规范 / Anti-Patterns / 操作指令）"
        ),
        "severity": "fail",
    },
    {
        "id": "B1_size_threshold",
        "title": "单个元资产文件行数 ≤ META_DOC_SPLIT_THRESHOLD_LINES",
        "severity": "warn",
    },
    {
        "id": "B2_cross_reference_graph",
        "title": "AGENT.md.skills + SKILL.md.depends + framework.json.features 引用图完整",
        "severity": "fail|warn",
    },
    {
        "id": "B3_manifest_drift",
        "title": "SKILL.md '## Layer 1 检查项' 段与 builtin CHECKS_MANIFEST 对账",
        "severity": "fail",
    },
    {
        "id": "B4_hardcoded_constants",
        "title": "SKILL.md / AGENT.md / 协议文档不得出现常量名对应的裸数值",
        "severity": "warn",
    },
    {
        "id": "B5_workflow_coverage_matrix",
        "title": "ORCHESTRATOR dispatch 表 × framework.json features × agents 覆盖矩阵",
        "severity": "warn",
    },
)
