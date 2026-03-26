#!/usr/bin/env python3
"""Stop Hook: Send a desktop notification when Claude Code finishes a task.

Cross-platform: Windows (WinRT toast), macOS (osascript), Linux (notify-send).
Falls back to console beep if no notification method is available.

Test:
  echo '{"stop_reason":"end_turn"}' | python .claude/hooks/notify_done.py
  Expected: desktop notification or beep
"""

import json
import subprocess
import sys


def notify_windows(title, message):
    """Windows toast via PowerShell WinRT."""
    ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null
$xml = [Windows.Data.Xml.Dom.XmlDocument]::new()
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text>{title}</text><text>{message}</text></binding></visual><audio silent="true"/></toast>')
$appId = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        timeout=10,
    )
    return True


def notify_macos(title, message):
    """macOS notification via osascript."""
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    return True


def notify_linux(title, message):
    """Linux notification via notify-send."""
    subprocess.run(["notify-send", title, message], capture_output=True, timeout=10)
    return True


def beep():
    """Console beep as last resort."""
    print("\a", end="", flush=True)


def main():
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        data = {}

    if data.get("stop_hook_active"):
        sys.exit(0)

    stop_reason = data.get("stop_reason", "completed")
    title = "Claude Code"
    message = f"Task finished ({stop_reason})"

    notified = False
    platform = sys.platform

    try:
        if platform == "win32":
            notified = notify_windows(title, message)
        elif platform == "darwin":
            notified = notify_macos(title, message)
        elif platform.startswith("linux"):
            notified = notify_linux(title, message)
    except Exception:
        pass

    if not notified:
        beep()

    sys.exit(0)


if __name__ == "__main__":
    main()
