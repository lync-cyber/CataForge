"""Module-level constants shared across framework-review checks."""

from __future__ import annotations

DEFAULT_META_SIZE = 500
DEFAULT_EVENT_LOG_DRIFT_MIN_EVENTS = 10
DEFAULT_RETRO_SELF_CAUSED = 5

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
B1_REQUIRED_SECTIONS_EXEMPT_SKILLS = frozenset(
    {
        "agent-dispatch",
        "research",
        "start-orchestrator",
        "tdd-engine",
        "workflow-framework-generator",
    }
)

B1_REQUIRED_SECTIONS_EXEMPT_AGENTS = frozenset(
    {
        "orchestrator",
    }
)

# Infrastructure skills called by orchestrator / main-thread or by
# other skills directly, not advertised in any AGENT.md skills: list.
# doc-review / doc-consistency are builtin-only Layer-1 engines invoked via
# `cataforge skill run` by the context review/consistency branches.
ORPHAN_SKILL_WHITELIST = frozenset(
    {
        "agent-dispatch",
        "tdd-engine",
        "change-guard",
        "start-orchestrator",
        "context",
        "doc-review",
        "doc-consistency",
        "research",
        "debug",
        "framework-update",
        "workflow-framework-generator",
        "platform-audit",
        "framework-review",
        "framework-issue-resolve",
        "framework-feedback",
        "framework-walkthrough",
    }
)

# Sub-agents not directly phase-routed but invoked by orchestrator or
# tdd-engine — counted as "referenced" so B5 doesn't warn on them.
B5_SUBAGENTS = frozenset({"test-writer", "implementer", "refactorer"})
B5_CROSS_CUTTING = frozenset(
    {
        "reviewer",
        "debugger",
        "orchestrator",
        "reflector",
    }
)
