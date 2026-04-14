"""PreToolUse Hook: Log agent_dispatch events before Agent tool execution.

Matcher: Agent
Never blocks (exit 0) — logging is best-effort.
"""

import re
import sys

from cataforge.hook.base import hook_main, matches_capability, read_hook_input


def _extract_task_type(prompt_text: str | None) -> str | None:
    if not prompt_text:
        return None
    m = re.search(r"任务类型:\s*(\S+)", prompt_text)
    return m.group(1).strip() if m else None


@hook_main
def main() -> None:
    data = read_hook_input()

    if not data or not matches_capability(data, "agent_dispatch"):
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    agent_id = tool_input.get("subagent_type")
    if not agent_id:
        sys.exit(0)

    prompt_text = tool_input.get("prompt") or ""
    task_type = _extract_task_type(prompt_text)
    description = tool_input.get("description") or ""

    detail = f"调度 {agent_id}: {description}" if description else f"调度 {agent_id}"
    print(
        f"[HOOK-INFO] agent_dispatch | agent={agent_id} task_type={task_type} | {detail}",
        file=sys.stderr,
    )

    sys.exit(0)


if __name__ == "__main__":
    main()
