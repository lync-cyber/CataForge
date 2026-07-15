"""OS-level process, command, and platform primitives."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time

from cataforge.utils.run_subprocess import run as run_proc

_PID_POLL_INTERVAL_SECONDS = 0.1

# Win32 constants — uppercase to match the public Win32 API names.
_WIN_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_WIN_STILL_ACTIVE = 259


def pid_alive(pid: int | None) -> bool:
    """Return True if *pid* identifies a live process on this host.

    Cross-platform: on POSIX uses ``os.kill(pid, 0)`` (no signal sent, just
    a permission/existence probe). On Windows uses ``OpenProcess`` via
    ctypes — sending signal 0 with ``os.kill`` on Windows actually calls
    ``TerminateProcess`` (Python docs), which would kill the very process
    we're inspecting.

    POSIX zombie handling: a child of *this* process that has exited but
    not been ``wait()``-ed for is a zombie. Its PID stays valid to
    ``kill(pid, 0)``, so a naïve probe would report "alive" indefinitely
    and ``stop()`` would loop forever after SIGTERM took effect. Probe with
    non-blocking ``waitpid`` first to reap the zombie if it's ours, so the
    return value reflects whether the process is meaningfully running, not
    just whether the PID-table entry survives. ``ChildProcessError`` (pid
    is not our child / already reaped) falls through to the kill probe.
    """
    import os

    if pid is None or pid <= 0:
        return False
    if sys.platform == "win32":
        return _pid_alive_windows(pid)
    try:
        reaped_pid, _status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        # Not our child (orphan re-parented to init, or already reaped).
        pass
    except OSError:
        return False
    else:
        # waitpid returned: 0 → child still running; pid → just-reaped zombie.
        if reaped_pid == pid:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by another user — counts as alive.
        return True
    except OSError:
        return False
    return True


def _pid_alive_windows(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined,unused-ignore]
    handle = kernel32.OpenProcess(_WIN_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == _WIN_STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _wait_for_pid_dead(pid: int, timeout: float) -> bool:
    """Poll until *pid* is gone or *timeout* elapses. Returns True if dead."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(_PID_POLL_INTERVAL_SECONDS)
    return not pid_alive(pid)


# ---------------------------------------------------------------------------
# Command helpers
# ---------------------------------------------------------------------------


def has_command(name: str) -> bool:
    """Return True if *name* is found on PATH."""
    return shutil.which(name) is not None


def run_cmd(
    cmd: list[str],
    *,
    cwd: str | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    """Run a command and return the CompletedProcess (never raises on non-zero).

    Thin shim over :func:`cataforge.utils.run_subprocess.run` retained for
    source compatibility with the existing penpot callers; new code should
    import ``run_proc`` directly.
    """
    return run_proc(cmd, cwd=cwd, timeout=timeout)


def get_command_version(cmd: list[str]) -> str:
    """Run *cmd* and return stdout stripped, or ``""`` on failure."""
    try:
        r = run_proc(cmd, timeout=10)
        return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


def detect_platform() -> str:
    """Return a simple platform tag: ``windows``, ``darwin``, or ``linux``."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"
