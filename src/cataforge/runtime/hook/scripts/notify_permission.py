"""Notification Hook: Alert user when the AI IDE is waiting for permission.

Cross-platform: Windows (WinRT toast), macOS (osascript), Linux (notify-send).
Falls back to console beep if no notification method is available.
"""

import sys
from typing import Any

from cataforge.runtime.hook.base import get_platform_display_name, hook_main, read_hook_input
from cataforge.runtime.hook.scripts.notify_util import send_notification


def _resolve_message(data: dict[str, Any]) -> str:
    # Claude Code Notification payloads carry ``message``; Codex
    # PermissionRequest payloads describe the pending call via
    # ``tool_input.description`` / ``tool_name``.
    tool_input = data.get("tool_input") or {}
    message = data.get("message") or tool_input.get("description")
    if not message and data.get("tool_name"):
        message = f"{data['tool_name']} requires approval"
    return str(message) if message else "Action requires approval"


@hook_main
def main() -> None:
    data = read_hook_input()

    message = _resolve_message(data)
    if len(message) > 200:
        message = message[:197] + "..."

    title = f"{get_platform_display_name()} - Permission Required"
    send_notification(title, message, urgency=True, beep_count=3)
    sys.exit(0)


if __name__ == "__main__":
    main()
