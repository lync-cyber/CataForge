"""Shared notification utilities for CataForge hooks.

Cross-platform: Windows (WinRT toast), macOS (osascript), Linux (notify-send).
Falls back to console beep if no notification method is available.
"""

import html
import subprocess
import sys


def send_notification(
    title: str, message: str, urgency: bool = False, beep_count: int = 1
) -> None:
    """Send desktop notification, fallback to console beep."""
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


def _notify_windows(title: str, message: str) -> bool:
    safe_title = html.escape(title)
    safe_msg = html.escape(message)
    toast_ns = "Windows.UI.Notifications"
    xml_ns = "Windows.Data.Xml.Dom"
    app_id = (
        "{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}"
        "\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe"
    )
    toast_xml = (
        f"<toast><visual><binding template=\"ToastGeneric\">"
        f"<text>{safe_title}</text><text>{safe_msg}</text>"
        f"</binding></visual><audio silent=\"true\"/></toast>"
    )
    ps_script = (
        f"[{toast_ns}.ToastNotificationManager,"
        f" {toast_ns}, ContentType = WindowsRuntime] | Out-Null\n"
        f"[{xml_ns}.XmlDocument,"
        f" {xml_ns}, ContentType = WindowsRuntime] | Out-Null\n"
        f"$xml = [{xml_ns}.XmlDocument]::new()\n"
        f"$xml.LoadXml('{toast_xml}')\n"
        f"$appId = '{app_id}'\n"
        f"[{toast_ns}.ToastNotificationManager]::CreateToastNotifier($appId)"
        f".Show([{toast_ns}.ToastNotification]::new($xml))"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        timeout=10,
    )
    return True


def _notify_macos(title: str, message: str) -> bool:
    safe_msg = message.replace('"', '\\"')
    script = f'display notification "{safe_msg}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    return True


def _notify_linux(title: str, message: str, urgency: bool = False) -> bool:
    args = ["notify-send"]
    if urgency:
        args.append("--urgency=critical")
    args.extend([title, message])
    subprocess.run(args, capture_output=True, timeout=10)
    return True
