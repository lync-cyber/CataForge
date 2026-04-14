"""Stop Hook: Send a desktop notification when the AI IDE finishes a task.

Cross-platform: Windows (WinRT toast), macOS (osascript), Linux (notify-send).
Falls back to console beep if no notification method is available.
"""

import sys

from cataforge.hook.base import get_platform_display_name, hook_main, read_hook_input
from cataforge.hook.scripts.notify_util import send_notification


@hook_main
def main() -> None:
    data = read_hook_input()

    if data.get("stop_hook_active"):
        sys.exit(0)

    stop_reason = data.get("stop_reason", "completed")
    platform_name = get_platform_display_name()
    send_notification(platform_name, f"Task finished ({stop_reason})", beep_count=1)
    sys.exit(0)


if __name__ == "__main__":
    main()
