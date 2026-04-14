"""Platform-agnostic data types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgentStatus(Enum):
    COMPLETED = "completed"
    NEEDS_INPUT = "needs_input"
    BLOCKED = "blocked"
    APPROVED = "approved"
    APPROVED_WITH_NOTES = "approved_with_notes"
    NEEDS_REVISION = "needs_revision"
    ROLLED_BACK = "rolled-back"


@dataclass
class DispatchRequest:
    agent_id: str
    task: str
    task_type: str
    input_docs: list[str]
    expected_output: str
    phase: str
    project_name: str
    background: bool = False
    max_turns: int | None = None
    review_path: str | None = None
    answers: dict[str, str] | None = None
    intermediate_outputs: list[str] | None = None
    resume_guidance: str | None = None
    change_analysis: str | None = None


@dataclass
class AgentResult:
    status: AgentStatus
    outputs: list[str]
    summary: str
    questions: list[dict[str, str]] | None = None
    completed_steps: str | None = None
    resume_guidance: str | None = None


# ---------------------------------------------------------------------------
# Capability IDs — core tool-level abstractions
# ---------------------------------------------------------------------------

CAPABILITY_IDS: list[str] = [
    "file_read",
    "file_write",
    "file_edit",
    "file_glob",
    "file_grep",
    "shell_exec",
    "web_search",
    "web_fetch",
    "user_question",
    "agent_dispatch",
]

# Capabilities that may legitimately be null on some platforms.
# Conformance checks emit INFO instead of WARN for these.
OPTIONAL_CAPABILITY_IDS: set[str] = {
    "user_question",   # Codex has no AskUserQuestion; Cursor support is partial
    "web_fetch",       # Cursor / Codex lack a native web-fetch tool
}

# Extended capability IDs — tools that exist on some platforms but are not
# part of the core 10.  Platforms declare support in profile.yaml
# ``extended_capabilities``.  Conformance treats these as INFO when missing.
EXTENDED_CAPABILITY_IDS: list[str] = [
    "notebook_edit",     # Jupyter notebook editing (Claude Code: NotebookEdit)
    "browser_preview",   # Browser automation / preview (Claude Code: preview_*, Cursor: computer)
    "image_input",       # Image/screenshot input (Codex: -i flag, OpenCode: drag-drop)
    "code_review",       # Dedicated code review tool (Codex: /review)
]

# ---------------------------------------------------------------------------
# Agent frontmatter fields — superset across all platforms
# ---------------------------------------------------------------------------

# Each platform declares its supported subset in profile.yaml
# ``agent_config.supported_fields``.  The translator and deployer use this
# to decide which fields to pass through vs. drop when targeting a platform.
AGENT_FRONTMATTER_FIELDS: list[str] = [
    # Universal (all platforms)
    "name",
    "description",
    "tools",
    "disallowedTools",
    "model",
    # Orchestration
    "maxTurns",
    "background",
    "effort",
    "isolation",
    # Extension points
    "skills",
    "mcpServers",
    "hooks",
    # Memory & context
    "memory",
    "initialPrompt",
    "prompt",
    # Permissions
    "permissionMode",
    # UI / display
    "color",
]

# ---------------------------------------------------------------------------
# Platform feature flags — higher-order behaviors beyond tool-level mapping
# ---------------------------------------------------------------------------

# Declared in profile.yaml ``features`` section.  These are boolean flags
# describing what a platform supports as a whole, not per-tool mappings.
PLATFORM_FEATURES: list[str] = [
    "cloud_agents",         # Remote/cloud agent execution (Cursor, Codex cloud)
    "agent_teams",          # Multi-session agent coordination (Claude Code)
    "parallel_agents",      # Concurrent agent execution (Cursor, Claude Code)
    "scheduled_tasks",      # Cron/scheduled agent execution (Claude Code, Cursor)
    "background_agents",    # Background agent execution within a session
    "plan_mode",            # Read-only planning mode
    "computer_use",         # Native UI/browser automation capability
    "realtime_voice",       # Voice input/output (Codex WebRTC)
    "multi_model",          # Per-task model selection / routing
    "session_resume",       # Session persistence and resume
    "worktree_isolation",   # Git worktree-based agent isolation
    "autonomy_slider",      # Configurable agent autonomy level (Cursor)
    "ci_cd_integration",    # Native CI/CD pipeline integration (OpenCode)
    "multi_root",           # Multi-project workspace (Codex --add-dir)
    "agent_memory",         # Agent-level persistent memory across sessions
    "plugin_marketplace",   # Plugin discovery and installation service
    "context_management",   # Context window management (chapters, compression)
]

# ---------------------------------------------------------------------------
# Permission / approval modes
# ---------------------------------------------------------------------------


class PermissionMode(Enum):
    """Platform-agnostic permission/approval modes.

    Each platform maps a subset of these to its native approval system.
    Declared in profile.yaml ``permissions.modes``.
    """

    DEFAULT = "default"                  # Standard prompts (Claude Code, OpenCode)
    ACCEPT_EDITS = "accept_edits"        # Auto-accept file edits (Claude Code)
    AUTO = "auto"                        # Classifier-based auto-approval (Claude Code, Codex)
    DONT_ASK = "dont_ask"               # Auto-deny prompts (Claude Code)
    BYPASS = "bypass"                    # Skip all permission prompts (Claude Code)
    PLAN = "plan"                        # Read-only exploration (Claude Code, OpenCode)
    READ_ONLY = "read_only"             # Consultative mode (Codex)
    FULL_ACCESS = "full_access"         # Unrestricted (Codex)


class SkillType(Enum):
    """Skill classification."""

    INSTRUCTIONAL = "instructional"
    EXECUTABLE = "executable"
    HYBRID = "hybrid"
