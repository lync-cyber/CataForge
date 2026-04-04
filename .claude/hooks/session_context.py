#!/usr/bin/env python3
"""SessionStart Hook: Inject plan summary and project context at session start.

Test:
  echo '{}' | python .claude/hooks/session_context.py
  Expected: JSON with additionalContext field (if plans exist)
"""

import json
import os
import sys

# Event logger integration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
try:
    from event_logger import append_event as _log_event
except ImportError:
    _log_event = None


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

    # Log session_start event
    if _log_event:
        phase = "unknown"
        claude_md = os.path.join(project_dir, "CLAUDE.md")
        if os.path.isfile(claude_md):
            try:
                with open(claude_md, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("- 当前阶段:"):
                            phase = line.split(":", 1)[1].strip().split("|")[0].strip()
                            break
            except OSError:
                pass
        try:
            _log_event(
                event="session_start",
                phase=phase,
                detail="会话启动",
            )
        except Exception:
            pass  # Never block on logging failure

    sys.exit(0)


if __name__ == "__main__":
    main()
