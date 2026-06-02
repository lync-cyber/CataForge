"""Shared CLI/script utilities — terminal output, process helpers, network checks.

Extracted from the former .cataforge/scripts/lib/_common.py for use by
hook scripts, skill scripts, doc tools, and integrations.
"""

from __future__ import annotations

import io
import locale
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

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


# The five primitives below are now thin wrappers over :mod:`cataforge.interface.cli.ui`
# so every caller (CLI subcommands, integrations, hook scripts) goes through
# the same colour/Unicode/TTY detection. The signatures are preserved to keep
# external callers source-compatible.


def section(msg: str) -> None:
    from cataforge.interface.cli.ui import ui as _ui

    _ui.section(msg)


def info(msg: str) -> None:
    from cataforge.interface.cli.ui import ui as _ui

    _ui.info(msg)


def ok(msg: str) -> None:
    from cataforge.interface.cli.ui import ui as _ui

    _ui.ok(msg)


def warn(msg: str) -> None:
    from cataforge.interface.cli.ui import ui as _ui

    _ui.warn(msg)


def fail(msg: str) -> None:
    from cataforge.interface.cli.ui import ui as _ui

    _ui.fail(msg)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def _preferred_encoding_is_utf8() -> bool:
    """True when this interpreter's default text encoding is already UTF-8."""
    enc = locale.getpreferredencoding(False)
    return enc.replace("-", "").replace("_", "").lower() == "utf8"


def ensure_utf8() -> None:
    """Make this Python process speak UTF-8 — for stdout, files, and subprocess I/O.

    Two-phase:

    1. **Relaunch under Python UTF-8 Mode** when the default text encoding is
       not already UTF-8 (idempotent, pytest-safe). A Windows ANSI code page
       (cp936/GBK on zh-CN) and a POSIX ``C``/``POSIX`` locale both resolve
       ``locale.getpreferredencoding(False)`` to a non-UTF-8 codec — which makes
       ``text=True`` subprocess calls crash on UTF-8 bytes from child processes
       and ``open()`` / ``read_text()`` mis-decode UTF-8 files. Setting
       ``PYTHONUTF8=1`` and relaunching flips ``sys.flags.utf8_mode`` on at the
       interpreter level, so default file I/O is UTF-8 with no per-callsite
       ``encoding="utf-8"`` plumbing needed.

       The relaunch replays ``sys.orig_argv`` verbatim with ``PYTHONUTF8=1`` in
       the environment. ``orig_argv`` preserves the exact original interpreter
       invocation — console-script launcher (run as a zipapp), ``-m module``,
       and plain ``python script.py`` all relaunch identically without inferring
       a module target. The env var (read at interpreter startup) flips
       ``utf8_mode`` on, so the relaunched process reads its default encoding as
       UTF-8 and does not relaunch again — idempotent, no loop.

       POSIX replaces the process image via ``os.execve`` — no extra PID, no
       lingering parent. Windows has no real ``exec`` (the CRT emulation crashes
       the interpreter mid-handoff with an access violation on non-trivial
       output), so it spawns a child and forwards the child's exit code.

       Skipped when running under pytest (detected via ``PYTEST_CURRENT_TEST``,
       ``PYTEST_VERSION``, or ``pytest`` already in ``sys.modules``). Critical
       for test collection: pytest imports test modules — which transitively
       import ``cataforge.interface.cli.main`` — before ``PYTEST_CURRENT_TEST`` is set,
       so the env-var check alone would relaunch into the wrong process.

    2. **Reconfigure stdout/stderr to UTF-8.** Belt-and-suspenders for the
       cases where phase 1 is a no-op (locale already UTF-8, already in UTF-8
       Mode, or under pytest).

    Idempotent — safe to call from CLI entry points and subscript ``main()``s.
    """
    # pytest imports test modules (which transitively import cataforge.interface.cli.main)
    # before PYTEST_CURRENT_TEST is set, so the env var alone is not enough —
    # `pytest in sys.modules` is the load-time-stable signal.
    under_pytest = (
        "PYTEST_CURRENT_TEST" in os.environ
        or "PYTEST_VERSION" in os.environ
        or "pytest" in sys.modules
    )
    needs_reexec = (
        not sys.flags.utf8_mode and not under_pytest and not _preferred_encoding_is_utf8()
    )
    if needs_reexec and sys.orig_argv:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        if sys.platform == "win32":
            # No real exec on Windows; spawn a child that inherits stdio so the
            # CLI writes straight to the terminal, then forward its exit code.
            completed = subprocess.run(  # allow-raw-subprocess: inherit stdio
                sys.orig_argv, env=env
            )
            sys.exit(completed.returncode)
        os.execve(sys.executable, sys.orig_argv, env)

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
    cwd = Path.cwd()
    path = cwd / ".env" if path is None else Path(path).resolve()

    try:
        if not path.is_relative_to(cwd):
            raise ValueError(f"load_dotenv: path is outside the working directory: {path}")
    except AttributeError:
        # Python < 3.9 fallback
        try:
            path.relative_to(cwd)
        except ValueError:
            raise ValueError(
                f"load_dotenv: path is outside the working directory: {path}"
            ) from None

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
