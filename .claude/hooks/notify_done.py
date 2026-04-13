#!/usr/bin/env python3
"""Stop Hook: Send a desktop notification when Claude Code finishes a task.

Cross-platform: Windows (WinRT toast), macOS (osascript), Linux (notify-send).
Falls back to console beep if no notification method is available.

Test:
  echo '{"stop_reason":"end_turn"}' | python .claude/hooks/notify_done.py
  Expected: desktop notification or beep
"""

import json
import sys

from _hook_base import hook_main, read_hook_input
from notify_util import send_notification


@hook_main
def main():
    data = read_hook_input()

    if data.get("stop_hook_active"):
        sys.exit(0)

    stop_reason = data.get("stop_reason", "completed")
    send_notification("Claude Code", f"Task finished ({stop_reason})", beep_count=1)
    sys.exit(0)


if __name__ == "__main__":
    main()
