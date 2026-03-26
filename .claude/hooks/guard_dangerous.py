#!/usr/bin/env python3
"""PreToolUse Hook: Block destructive Bash commands before execution.

Test:
  echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf ."}}' | python .claude/hooks/guard_dangerous.py
  Expected: exit 2, stderr shows block reason

  echo '{"tool_name":"Bash","tool_input":{"command":"git status"}}' | python .claude/hooks/guard_dangerous.py
  Expected: exit 0, no output
"""

import json
import re
import sys

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


def main():
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = (data.get("tool_input") or {}).get("command", "")
    if not command:
        sys.exit(0)

    for pattern, reason, suggestion in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            print(f"BLOCKED: {reason}", file=sys.stderr)
            print(f"Command: {command}", file=sys.stderr)
            print(f"Suggestion: {suggestion}", file=sys.stderr)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
