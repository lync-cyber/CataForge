"""UTF-8 encoding bootstrap for CLI entry points and standalone scripts."""

from __future__ import annotations

import io
import locale
import os
import subprocess
import sys


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

       The relaunch preserves ``sys.orig_argv[1:]`` and replaces argv[0] with
       ``sys.executable``.  The replacement is important for launchers such as
       uv's Windows trampoline: ``orig_argv[0]`` can name the base interpreter
       even though ``sys.executable`` correctly names the isolated tool
       environment.  Reusing the base interpreter loses the tool's
       ``site-packages`` and fails with ``ModuleNotFoundError``.  The remaining
       arguments preserve console-script launchers (run as zipapps), ``-m
       module``, and plain ``python script.py`` without inferring a module
       target. The env var (read at interpreter startup) flips
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
        # Never trust orig_argv[0] as the environment identity.  uv's Windows
        # trampoline exposes the base interpreter there while sys.executable
        # points at the tool venv; replaying orig_argv verbatim therefore drops
        # the installed package on relaunch.
        relaunch_argv = [sys.executable, *sys.orig_argv[1:]]
        if sys.platform == "win32":
            # No real exec on Windows; spawn a child that inherits stdio so the
            # CLI writes straight to the terminal, then forward its exit code.
            completed = subprocess.run(  # allow-raw-subprocess: inherit stdio
                relaunch_argv, env=env
            )
            sys.exit(completed.returncode)
        os.execve(sys.executable, relaunch_argv, env)

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
        elif hasattr(stream, "buffer"):
            wrapper = io.TextIOWrapper(
                stream.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )
            setattr(sys, stream_name, wrapper)
