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
        "id": "B2_suggested_tools_valid",
        "title": (
            "SKILL.md suggested-tools ∈ CAPABILITY_IDS ∪ EXTENDED_CAPABILITY_IDS "
            "(capability_id 规范, deploy 翻译为平台原生名; 原生名如 Read/Bash 不可移植)"
        ),
        "severity": "fail",
    },
    {
        "id": "B3_manifest_drift",
        "title": "SKILL.md '## Layer 1 检查项' 段与 builtin CHECKS_MANIFEST 对账",
        "severity": "fail",
    },
    {
        "id": "B3_rules_schema_compliance",
        "title": (
            "项目级 .cataforge/skills/<skill>/rules/*.yaml plugin "
            "覆写文件 schema 校验 (cataforge.runtime.skill.rules.loader)"
        ),
        "severity": "fail",
    },
    {
        "id": "B3_baseline_provenance",
        "title": (
            ".cataforge/baselines/*.json 变更必须与 docs/reviews/code/CODE-SCAN-*.md "
            "报告同变更集（工作区与最近 commit 两级对账，防篡改基线过门禁）"
        ),
        "severity": "fail",
    },
    {
        "id": "B4_hardcoded_constants",
        "title": "SKILL.md / AGENT.md / 协议文档不得出现常量名对应的裸数值",
        "severity": "warn",
    },
    {
        "id": "B5_workflow_coverage_matrix",
        "title": "ORCHESTRATOR dispatch 表 × agents 覆盖矩阵 (phase→agent 单跳)",
        "severity": "warn",
    },
    {
        "id": "B5_phase_skill_coverage",
        "title": (
            "phase → agent → skill 三跳: 每个 phase-routed agent 必须声明 "
            "≥1 skill 且引用的 skill 必须存在"
        ),
        "severity": "warn",
    },
    {
        "id": "B5_eventlog_agent_return_drift",
        "title": (
            "EVENT-LOG.jsonl agent_return 事件与 phase routing 对账 "
            "(总事件 ≥ 阈值时 phase-routed agent 0 returns → FAIL，"
            "ref 字段缺失 → WARN，未达阈值 → INFO)"
        ),
        "severity": "fail|warn|info",
    },
    {
        "id": "B5_feature_phase_alignment",
        "title": (
            "framework.json features[*].phase_guard 必须命中 ORCHESTRATOR "
            "Phase Routing 中的已知 phase"
        ),
        "severity": "warn",
    },
    {
        "id": "B5_hook_installed",
        "title": (
            "validate_agent_result PostToolUse hook 必须在 hooks.yaml "
            "中以 matcher_capability=agent_dispatch 注册"
        ),
        "severity": "fail",
    },
    {
        "id": "B5_interactive_host",
        "title": (
            "framework.json#/workflow 中 interactive=true 的 phase 必须 "
            "execution_host=inline（除非平台 features.subagent_interactive=true；"
            "带 interactive_subagent_ack 时降级为 INFO）"
        ),
        "severity": "fail|info",
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
        "id": "B6_hook_policy_coverage",
        "title": (
            "每个 platform profile.yaml 的 hooks.policies 必须覆盖且仅覆盖 hooks.yaml 引用的 script"
        ),
        "severity": "warn",
    },
    {
        "id": "B6_hook_manifest_drift",
        "title": (
            "hooks.yaml 非 custom: 脚本必须 ∈ cataforge.runtime.hook.manifest."
            "HOOKS_MANIFEST (orphan WARN, missing FAIL)"
        ),
        "severity": "fail|warn",
    },
    {
        "id": "B7_model_tier_value",
        "title": (
            "AGENT.md model_tier ∈ {light, standard, heavy, inherit, none} "
            "且与 constants.AGENT_MODEL_DEFAULTS 一致；heavy 需进 "
            "AGENT_MODEL_TIER_HEAVY_WHITELIST"
        ),
        "severity": "fail|warn",
    },
    {
        "id": "B7_legacy_model_field",
        "title": (
            "AGENT.md 仍使用 legacy 'model: <id>' 而非 model_tier "
            "(直接迁移, 无过渡期, deploy 会丢弃 legacy model)"
        ),
        "severity": "fail",
    },
    {
        "id": "B7_platform_tier_map",
        "title": (
            "platform profile.yaml model_routing.tier_map 必须覆盖 "
            "light/standard/heavy (per_agent_model=true 且 user_resolved=false 时)"
        ),
        "severity": "warn",
    },
    {
        "id": "B8_anti_pattern_section_present",
        "title": (
            "每个非豁免 skill / agent 的 SKILL.md / AGENT.md 应有 "
            "'## Anti-Patterns' 段（缺失 WARN，留作 backlog 渐进补齐）"
        ),
        "severity": "warn",
    },
    {
        "id": "B8_anti_pattern_floor",
        "title": (
            "Anti-Patterns bullet 数量 ≥ ANTI_PATTERN_MIN_COUNT_SKILL "
            "(skill, 默认 3) / ANTI_PATTERN_MIN_COUNT_AGENT (agent, 默认 4)"
        ),
        "severity": "fail",
    },
    {
        "id": "B8_anti_pattern_substantive",
        "title": ("Anti-Patterns 每条 bullet 正文 ≥ 12 字符 (过滤 placeholder 占位条目)"),
        "severity": "warn",
    },
    {
        "id": "B9_migration_path_validity",
        "title": (
            "migration_checks 活跃条目: editable 树下 src/ 路径必须存在; "
            "allow_missing 仅对 file_must_not_contain 有效"
        ),
        "severity": "warn",
    },
    {
        "id": "B9_migration_deprecate_order",
        "title": ("migration_checks deprecate_after > release_version (否则发布即废弃, 永不执行)"),
        "severity": "warn",
    },
    {
        "id": "B9_migration_dead_entry",
        "title": ("migration_checks 已废弃且路径缺失的死条目提示 (建议从 framework.json 移除)"),
        "severity": "info",
    },
)
