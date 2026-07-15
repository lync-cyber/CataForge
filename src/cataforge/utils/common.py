"""Shared CLI/script utilities — terminal output, process helpers, network checks.

Extracted from the former .cataforge/scripts/lib/_common.py for use by
hook scripts, skill scripts, doc tools, and integrations.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

from cataforge.utils.console import get_console
from cataforge.utils.run_subprocess import run as run_proc

# ---------------------------------------------------------------------------
# Terminal colour constants (ANSI escape codes)
# ---------------------------------------------------------------------------

BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
NC = "\033[0m"  # No Color / reset

# ---------------------------------------------------------------------------
# Structured terminal output helpers
# ---------------------------------------------------------------------------


# The five primitives below are thin wrappers over the active console
# (``cataforge.utils.console.get_console()``) so every caller (CLI subcommands,
# integrations, hook scripts) shares the same renderer. The interface layer
# installs its rich renderer at CLI start-up; outside a CLI process the default
# unstyled console handles output.


def section(msg: str) -> None:
    get_console().section(msg)


def info(msg: str) -> None:
    get_console().info(msg)


def ok(msg: str) -> None:
    get_console().ok(msg)


def warn(msg: str) -> None:
    get_console().warn(msg)


def fail(msg: str) -> None:
    get_console().fail(msg)


# ---------------------------------------------------------------------------
# Process / command helpers
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
