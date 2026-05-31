"""Module-level constants shared across framework-review checks."""

from __future__ import annotations

DEFAULT_META_SIZE = 500
DEFAULT_EVENT_LOG_DRIFT_MIN_EVENTS = 10

VALID_MODEL_TIERS = frozenset({"light", "standard", "heavy", "inherit", "none"})

REQUIRED_SECTIONS_SKILL = {
    "能力边界": r"^##\s+能力边界",
    "输入定义": r"^##\s+(输入规范|调度输入|输入|Input(\s+Contract)?)",
    "输出定义": r"^##\s+(输出规范|输出|Output(\s+Contract)?|返回值|执行结果)",
    "操作步骤": (
        r"^##\s+(操作指令|执行流程|执行步骤|执行|步骤|"
        r"角色假设|平台调度实现|Anti-?Patterns)"
    ),
}

REQUIRED_SECTIONS_AGENT = {
    "Identity": r"^##\s+(Identity|身份|角色)",
    "Input Contract": r"^##\s+(Input Contract|输入契约|输入规范)",
    "Output Contract": r"^##\s+(Output Contract|输出契约|输出规范)",
    "Anti-Patterns": r"^##\s+Anti-?Patterns",
}

# Skills whose SKILL.md serves a different role than the canonical
# 能力边界/输入/输出/Anti-Patterns shape — runtime adapters, macro
# orchestration skills, scaffold generators.
B1_REQUIRED_SECTIONS_EXEMPT_SKILLS = frozenset({
    "agent-dispatch",
    "research",
    "start-orchestrator",
    "tdd-engine",
    "workflow-framework-generator",
})

B1_REQUIRED_SECTIONS_EXEMPT_AGENTS = frozenset({
    "orchestrator",
})

# Infrastructure skills called by orchestrator / main-thread or by
# other skills directly, not advertised in any AGENT.md skills: list.
# doc-review / doc-consistency are builtin-only Layer-1 engines invoked via
# `cataforge skill run` by the context review/consistency branches.
ORPHAN_SKILL_WHITELIST = frozenset({
    "agent-dispatch",
    "tdd-engine",
    "change-guard",
    "start-orchestrator",
    "context",
    "doc-review",
    "doc-consistency",
    "research",
    "debug",
    "self-update",
    "workflow-framework-generator",
    "platform-audit",
    "framework-review",
    "framework-issue-resolve",
    "framework-feedback",
    "framework-walkthrough",
})

# Constants whose names must be referenced instead of bare numerics.
# (constant_name, numeric_pattern, doc_hint)
CONSTANT_LITERALS: tuple[tuple[str, str, str], ...] = (
    ("MAX_QUESTIONS_PER_BATCH", r"≤\s*3\s*(问|题|个问题)", "≤3 问"),
    ("DOC_SPLIT_THRESHOLD_LINES", r"(>|超过|≥)\s*300\s*行", ">300 行"),
    ("DOC_REVIEW_L2_SKIP_THRESHOLD_LINES", r"<\s*200\s*行", "<200 行"),
    ("TDD_LIGHT_LOC_THRESHOLD", r"(≤|<|>)\s*150\s*(LOC|loc|行代码)", "150 LOC 阈值"),
    ("RETRO_TRIGGER_SELF_CAUSED", r"(累计|≥)\s*5\s*条", "≥5 条"),
    ("SPRINT_REVIEW_MICRO_TASK_COUNT", r"(≤|<=)\s*3\s*个任务", "≤3 个任务"),
)

# Sub-agents not directly phase-routed but invoked by orchestrator or
# tdd-engine — counted as "referenced" so B5 doesn't warn on them.
B5_SUBAGENTS = frozenset({"test-writer", "implementer", "refactorer"})
B5_CROSS_CUTTING = frozenset({
    "reviewer", "debugger", "orchestrator", "reflector",
})
