#!/usr/bin/env python3
"""SessionStart Hook: Inject plan summary and project context at session start.

Test:
  echo '{}' | python .claude/hooks/session_context.py
  Expected: JSON with additionalContext field (if plans exist)
"""

import json
import os
import sys


def main():
    # Locate project root (two levels up from hooks/)
    hooks_dir = os.path.dirname(os.path.abspath(__file__))
    claude_dir = os.path.dirname(hooks_dir)
    project_dir = os.path.dirname(claude_dir)

    context_parts = []

    # Check for active plan
    plan_path = os.path.join(project_dir, ".claude", "plans", "PLAN.md")
    if os.path.isfile(plan_path):
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= 20:
                        break
                    lines.append(line.rstrip())
            if lines:
                plan_summary = "\n".join(lines).strip()
                context_parts.append(
                    f"=== Active Plan (.claude/plans/PLAN.md) ===\n{plan_summary}\n..."
                )
        except OSError:
            pass

    # List plan files
    plans_dir = os.path.join(project_dir, ".claude", "plans")
    if os.path.isdir(plans_dir):
        try:
            plan_files = [f for f in os.listdir(plans_dir) if f.endswith(".md")]
            if plan_files:
                context_parts.append(
                    f"Plan files available: {', '.join(sorted(plan_files))}"
                )
        except OSError:
            pass

    if context_parts:
        context_text = "\n\n".join(context_parts)
        output = json.dumps({"additionalContext": context_text}, ensure_ascii=False)
        print(output)

    sys.exit(0)


if __name__ == "__main__":
    main()
