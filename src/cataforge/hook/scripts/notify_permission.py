"""Notification Hook: Alert user when the AI IDE is waiting for permission.

Cross-platform: Windows (WinRT toast), macOS (osascript), Linux (notify-send).
Falls back to console beep if no notification method is available.
"""

import sys

from cataforge.hook.base import hook_main, read_hook_input
from cataforge.hook.scripts.notify_util import send_notification


@hook_main
def main() -> None:
    data = read_hook_input()

    message = data.get("message", "Action requires approval")
    if len(message) > 200:
        message = message[:197] + "..."

    send_notification(
        "Claude Code - Permission Required", message, urgency=True, beep_count=3
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
