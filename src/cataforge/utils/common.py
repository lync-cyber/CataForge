"""Shared CLI/script utilities — terminal output, process helpers, network checks.

Extracted from the former .cataforge/scripts/lib/_common.py for use by
hook scripts, skill scripts, doc tools, and integrations.
"""

from __future__ import annotations

import io
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

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


def section(msg: str) -> None:
    print(f"\n{BOLD}[*] {msg}{NC}")


def info(msg: str) -> None:
    print(f"  {DIM}\u2139 {msg}{NC}")


def ok(msg: str) -> None:
    print(f"  {GREEN}\u2714 {msg}{NC}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}\u26a0 {msg}{NC}", file=sys.stderr)


def fail(msg: str) -> None:
    print(f"  {RED}\u2716 {msg}{NC}", file=sys.stderr)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def ensure_utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8, preventing encoding crashes on Windows."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
        elif hasattr(stream, "buffer"):
            wrapper = io.TextIOWrapper(
                stream.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )
            setattr(sys, stream_name, wrapper)


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
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Run a command and return the CompletedProcess (never raises on non-zero)."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
        **kwargs,
    )


def get_command_version(cmd: list[str]) -> str:
    """Run *cmd* and return stdout stripped, or ``""`` on failure."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
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


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------


def is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if something is listening on *host:port*."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect((host, port))
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def check_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if *port* is free (nothing listening)."""
    return not is_port_listening(port, host)


def find_available_port(start_port: int, label: str = "") -> int:
    """Return *start_port* if free, otherwise try the next 20 ports."""
    for offset in range(20):
        port = start_port + offset
        if check_port_available(port):
            if offset > 0 and label:
                info(f"{label} 端口 {start_port} 被占用，改用 {port}")
            return port
    return start_port


# ---------------------------------------------------------------------------
# .env file helper
# ---------------------------------------------------------------------------


def load_dotenv(path: str | Path | None = None, *, set_env: bool = False) -> dict[str, str]:
    """Load a .env file into a dict. Optionally set into os.environ."""
    path = Path.cwd() / ".env" if path is None else Path(path)

    result: dict[str, str] = {}
    if not path.is_file():
        return result

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("\"'")
        result[key] = val
        if set_env:
            os.environ.setdefault(key, val)

    return result
