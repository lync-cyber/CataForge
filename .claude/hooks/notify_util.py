#!/usr/bin/env python3
"""Shared notification utilities for CataForge hooks.

Cross-platform: Windows (WinRT toast), macOS (osascript), Linux (notify-send).
Falls back to console beep if no notification method is available.
"""

import html
import subprocess
import sys


def send_notification(
    title: str, message: str, urgency: bool = False, beep_count: int = 1
):
    """Send desktop notification, fallback to console beep.

    Args:
        title: Notification title.
        message: Notification body text.
        urgency: If True, use critical urgency on Linux.
        beep_count: Number of console beeps if notification fails.
    """
    notified = False
    platform = sys.platform

    try:
        if platform == "win32":
            notified = _notify_windows(title, message)
        elif platform == "darwin":
            notified = _notify_macos(title, message)
        elif platform.startswith("linux"):
            notified = _notify_linux(title, message, urgency)
    except Exception:
        pass

    if not notified:
        print("\a" * beep_count, end="", flush=True)


def _notify_windows(title, message):
    """Windows toast via PowerShell WinRT."""
    safe_title = html.escape(title)
    safe_msg = html.escape(message)
    ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null
$xml = [Windows.Data.Xml.Dom.XmlDocument]::new()
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text>{safe_title}</text><text>{safe_msg}</text></binding></visual><audio silent="true"/></toast>')
$appId = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        timeout=10,
    )
    return True


def _notify_macos(title, message):
    """macOS notification via osascript."""
    safe_msg = message.replace('"', '\\"')
    script = f'display notification "{safe_msg}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    return True


def _notify_linux(title, message, urgency=False):
    """Linux notification via notify-send."""
    args = ["notify-send"]
    if urgency:
        args.append("--urgency=critical")
    args.extend([title, message])
    subprocess.run(args, capture_output=True, timeout=10)
    return True
