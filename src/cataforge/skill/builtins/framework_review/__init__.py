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
    {
        "id": "B6_hook_script_reachability",
        "title": "hooks.yaml 引用的 script 必须解析到真实 .py 文件 (builtin / custom)",
        "severity": "fail",
    },
    {
        "id": "B6_hook_script_syntax",
        "title": "每个 hook script .py 必须 ast.parse 成功",
        "severity": "fail",
    },
    {
        "id": "B6_hook_matcher_capability",
        "title": "matcher_capability 必须是 CAPABILITY_IDS / EXTENDED_CAPABILITY_IDS 成员",
        "severity": "fail",
    },
    {
        "id": "B6_hook_degradation_coverage",
        "title": (
            "每个 platform profile.yaml 的 hooks.degradation 必须覆盖且仅覆盖 "
            "hooks.yaml 引用的 script"
        ),
        "severity": "warn",
    },
)
