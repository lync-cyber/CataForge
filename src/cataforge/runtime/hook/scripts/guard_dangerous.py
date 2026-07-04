"""PreToolUse Hook: Block destructive Bash commands before execution.

Test:
  echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf ."}}' \
    | python -m cataforge.runtime.hook.scripts.guard_dangerous
  Expected: exit 2, stderr shows block reason
"""

import os
import re
import sys

from cataforge.runtime.hook.base import matches_capability, matches_script_filters, read_hook_input

# Active only when the unattended building-loop set CATAFORGE_UNATTENDED — a
# tool-level safety net for guarantees PROMPT text alone can't enforce (an
# autonomous agent may ignore prose). No-op in normal interactive sessions.
UNATTENDED_BLOCKED_PATTERNS = [
    (
        r"git\s+merge\b",
        "无人值守禁止 merge",
        "无人循环只到 sprint building 完成 + PR 待审，合并须人工晨检",
    ),
    (
        r"gh\s+pr\s+merge\b",
        "无人值守禁止 PR merge",
        "PR 合并是人工 go/no-go 决策",
    ),
    (
        r"git\s+push\s+.*\bmain\b",
        "无人值守禁止推送 main",
        "无人循环只动 feature 分支",
    ),
]

DANGEROUS_PATTERNS = [
    (
        r"rm\s+-rf",
        "Recursive force delete detected",
        "Use trash-cli: npx trash-cli <path>",
    ),
    (r"rm\s+-r\s", "Recursive delete detected", "Use trash-cli: npx trash-cli <path>"),
    (
        r"rmdir\s+/s\s+/q",
        "Windows recursive silent delete detected",
        "Use trash-cli or review files first",
    ),
    (
        r"del\s+/s\s+/q",
        "Windows recursive silent delete detected",
        "Use trash-cli or delete files individually",
    ),
    (
        r"format\s+[a-zA-Z]:",
        "Disk format command detected",
        "This operation is not reversible",
    ),
    (
        r"git\s+push\s+.*--force(?!-)",
        "Force push detected",
        "Use --force-with-lease for safer force push",
    ),
    (
        r"git\s+reset\s+--hard",
        "Hard reset detected — may discard uncommitted work",
        "Use git stash first, or git reset --soft",
    ),
    (
        r"git\s+clean\s+-f",
        "git clean -f removes untracked files permanently",
        "Use git clean -n (dry run) first",
    ),
]


def _block(reason: str, command: str, suggestion: str) -> None:
    print(f"BLOCKED: {reason}", file=sys.stderr)
    print(f"Command: {command}", file=sys.stderr)
    print(f"Suggestion: {suggestion}", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    data = read_hook_input()

    if not matches_capability(data, "shell_exec"):
        sys.exit(0)

    command = (data.get("tool_input") or {}).get("command", "")
    if not command:
        sys.exit(0)

    # Unattended deny layer runs ahead of the v2 filters — a hard safety net
    # that project-local allow-lists must not be able to widen.
    if os.environ.get("CATAFORGE_UNATTENDED") == "1":
        for pattern, reason, suggestion in UNATTENDED_BLOCKED_PATTERNS:
            if re.search(pattern, command):
                _block(reason, command, suggestion)

    # v2 schema opt-in filters (matcher_command_pattern etc.).  The built-in
    # DANGEROUS_PATTERNS list still runs; v2 filters additionally narrow the
    # guard (e.g. project-local allow-lists) when declared.
    if not matches_script_filters(data, "guard_dangerous"):
        sys.exit(0)

    for pattern, reason, suggestion in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            _block(reason, command, suggestion)

    sys.exit(0)


if __name__ == "__main__":
    main()
