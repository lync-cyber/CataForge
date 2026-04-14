#!/usr/bin/env python3
"""Notification Hook: Alert user when Claude Code is waiting for permission.

Cross-platform: Windows (WinRT toast), macOS (osascript), Linux (notify-send).
Falls back to console beep if no notification method is available.

Test:
  echo '{"message":"Claude wants to run: git push"}' | python .cataforge/hooks/notify_permission.py
  Expected: desktop notification or beep
"""

import json
import sys

from _hook_base import hook_main, read_hook_input
from notify_util import send_notification


@hook_main
def main():
    data = read_hook_input()

    message = data.get("message", "Action requires approval")

    # Truncate long messages
    if len(message) > 200:
        message = message[:197] + "..."

    send_notification(
        "Claude Code - Permission Required", message, urgency=True, beep_count=3
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
