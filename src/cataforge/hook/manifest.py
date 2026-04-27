"""HOOKS_MANIFEST — authoritative catalog of builtin hook scripts.

Every entry declares an actual hook target. Helper modules like
``notify_util`` are intentionally absent from this manifest because they
are not meant to be wired as hooks themselves; wiring them in
hooks.yaml would be a subtle bug that ``B6_hook_script_reachability``
(file-existence check) cannot catch.

framework-review B6-ε validates that every non-``custom:`` script
referenced in ``.cataforge/hooks/hooks.yaml`` appears in this manifest.
That gives us a single registration point for "what hooks ship with
cataforge" and prevents `script: notify_util` from quietly deploying.

Schema (per entry):
    name (str)                 — script module name (matches .py filename)
    events (tuple[str, ...])   — Claude Code hook events the script can attach to
    default_capability (str|None) — typical matcher_capability; None for events
                                   without per-tool matchers (Stop/Notification/SessionStart)
    default_type (str)         — "block" or "observe"
    description (str)          — one-line purpose label
    safety_critical (bool)     — true for hooks whose absence has security
                                  implications (defaults to False)

Adding a new builtin hook script:
    1. Implement under cataforge/hook/scripts/<name>.py
    2. Register an entry here (single source of truth)
    3. Wire it into .cataforge/hooks/hooks.yaml
    4. Add a degradation_template entry (per-platform fallback)
"""

from __future__ import annotations

HOOKS_MANIFEST: tuple[dict[str, object], ...] = (
    {
        "name": "guard_dangerous",
        "events": ("PreToolUse",),
        "default_capability": "shell_exec",
        "default_type": "block",
        "description": "危险命令拦截",
        "safety_critical": True,
    },
    {
        "name": "log_agent_dispatch",
        "events": ("PreToolUse",),
        "default_capability": "agent_dispatch",
        "default_type": "observe",
        "description": "子代理调度审计",
        "safety_critical": False,
    },
    {
        "name": "validate_agent_result",
        "events": ("PostToolUse",),
        "default_capability": "agent_dispatch",
        "default_type": "observe",
        "description": "子代理返回值验证",
        "safety_critical": False,
    },
    {
        "name": "lint_format",
        "events": ("PostToolUse",),
        "default_capability": "file_edit",
        "default_type": "observe",
        "description": "文件编辑后自动格式化",
        "safety_critical": False,
    },
    {
        "name": "detect_correction",
        "events": ("PostToolUse",),
        "default_capability": "user_question",
        "default_type": "observe",
        "description": "用户纠正信号捕获 (option-override)",
        "safety_critical": False,
    },
    {
        "name": "detect_review_flag",
        "events": ("PostToolUse",),
        "default_capability": "agent_dispatch",
        "default_type": "observe",
        "description": "审查纠正信号捕获 (review-flag)",
        "safety_critical": False,
    },
    {
        "name": "notify_done",
        "events": ("Stop",),
        "default_capability": None,
        "default_type": "observe",
        "description": "会话结束通知",
        "safety_critical": False,
    },
    {
        "name": "notify_permission",
        "events": ("Notification",),
        "default_capability": None,
        "default_type": "observe",
        "description": "权限请求通知",
        "safety_critical": False,
    },
    {
        "name": "session_context",
        "events": ("SessionStart",),
        "default_capability": None,
        "default_type": "observe",
        "description": "会话初始化",
        "safety_critical": False,
    },
)


def manifest_names() -> frozenset[str]:
    """Return the set of script names in HOOKS_MANIFEST.

    Convenience for callers that only need name lookup (e.g. B6-ε
    drift check).
    """
    return frozenset(str(entry["name"]) for entry in HOOKS_MANIFEST)
