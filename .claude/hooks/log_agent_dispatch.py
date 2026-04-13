#!/usr/bin/env python3
"""PreToolUse Hook: Log agent_dispatch events before Agent tool execution.

Matcher: Agent
Never blocks (exit 0) — logging is best-effort.

Test:
  echo '{"tool_name":"Agent","tool_input":{"subagent_type":"architect","prompt":"任务类型: new_creation\\n执行架构设计"}}' | python .claude/hooks/log_agent_dispatch.py
  Expected: exit 0, agent_dispatch event appended to EVENT-LOG.jsonl
"""

import json
import os
import re
import sys

from _hook_base import hook_main, read_hook_input

# Shared utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
try:
    from event_logger import append_event as _log_event
except ImportError:
    _log_event = None

try:
    from phase_reader import read_current_phase
except ImportError:
    read_current_phase = None


def _extract_task_type(prompt_text):
    """Extract task_type from prompt text (matches '任务类型: xxx' pattern)."""
    if not prompt_text:
        return None
    m = re.search(r"任务类型:\s*(\S+)", prompt_text)
    if m:
        return m.group(1).strip()
    return None


@hook_main
def main():
    if not _log_event:
        sys.exit(0)

    data = read_hook_input()

    if not data or data.get("tool_name") != "Agent":
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    agent_id = tool_input.get("subagent_type")
    if not agent_id:
        # Not a CataForge agent dispatch (e.g. general-purpose agent)
        sys.exit(0)

    prompt_text = tool_input.get("prompt") or ""
    task_type = _extract_task_type(prompt_text)
    description = tool_input.get("description") or ""

    phase = "unknown"
    if read_current_phase:
        try:
            phase = read_current_phase()
        except Exception as e:
            print(f"[HOOK-WARN] {e}", file=sys.stderr)

    try:
        _log_event(
            event="agent_dispatch",
            phase=phase,
            agent=agent_id,
            task_type=task_type,
            detail=f"调度 {agent_id}: {description}"
            if description
            else f"调度 {agent_id}",
        )
    except Exception as e:
        print(f"[HOOK-WARN] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
