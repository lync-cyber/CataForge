"""MCP server lifecycle management — start, stop, persisted state.

Crash recovery and cross-process correctness:

* ``start()`` first reads the persisted JSON state from ``.cataforge/.mcp-
  state/<id>.json`` and verifies the recorded PID is actually alive (cross-
  platform check). A stale "running" state from a previous CLI invocation
  whose process has since died is cleaned up so the next start succeeds
  instead of silently refusing.
* ``stop()`` sends SIGTERM, waits for the PID to disappear (up to
  ``stop_timeout_seconds``), then escalates to SIGKILL on POSIX (Windows
  SIGTERM already maps to ``TerminateProcess``, which is forceful). The
  final state records ``stopped`` only after the PID is confirmed gone.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.mcp.registry import MCPRegistry
from cataforge.schema.mcp_spec import MCPServerSpec, MCPServerState

logger = logging.getLogger("cataforge.mcp.lifecycle")

DEFAULT_STOP_TIMEOUT_SECONDS = 5.0
_PID_POLL_INTERVAL_SECONDS = 0.1
# Windows has no SIGKILL — SIGTERM there is already TerminateProcess.
_SIGKILL = getattr(signal, "SIGKILL", signal.SIGTERM)


def _pid_alive(pid: int | None) -> bool:
    """Return True if *pid* identifies a live process on this host.

    Cross-platform: on POSIX uses ``os.kill(pid, 0)`` (no signal sent, just
    a permission/existence probe). On Windows uses ``OpenProcess`` via
    ctypes — sending signal 0 with ``os.kill`` on Windows actually calls
    ``TerminateProcess`` (Python docs), which would kill the very process
    we're inspecting.
    """
    if pid is None or pid <= 0:
        return False
    if sys.platform == "win32":
        return _pid_alive_windows(pid)
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


# Win32 constants — uppercase to match the public Win32 API names; ruff
# N806 would flag them as locals, so they're module-level.
_WIN_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_WIN_STILL_ACTIVE = 259


def _pid_alive_windows(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(
        _WIN_PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
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
        if not _pid_alive(pid):
            return True
        time.sleep(_PID_POLL_INTERVAL_SECONDS)
    return not _pid_alive(pid)


class MCPLifecycleManager:
    """Manage MCP server processes with persisted, cross-process-correct state."""

    def __init__(
        self,
        project_root: Path | None = None,
        registry: MCPRegistry | None = None,
        *,
        stop_timeout_seconds: float = DEFAULT_STOP_TIMEOUT_SECONDS,
    ) -> None:
        self._paths = ProjectPaths(project_root or find_project_root())
        self._registry = registry or MCPRegistry(self._paths.root)
        self._state_dir = self._paths.mcp_state_dir
        self._stop_timeout = stop_timeout_seconds

    def start(self, server_id: str) -> MCPServerState:
        """Start an MCP server, honouring persisted state across CLI runs."""
        spec = self._registry.get_server(server_id)
        if spec is None:
            raise ValueError(f"Unknown MCP server: {server_id}")

        persisted = self._load_state(server_id)
        if persisted and persisted.status == "running":
            if _pid_alive(persisted.pid):
                return persisted
            logger.info(
                "MCP %s: stale 'running' state (pid=%s) — process gone, restarting",
                server_id,
                persisted.pid,
            )
            self._delete_state(server_id)

        self._state_dir.mkdir(parents=True, exist_ok=True)

        try:
            cmd = [spec.command] + spec.args
            env = self._build_env(spec)

            proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(self._paths.root),
            )

            new_state = MCPServerState(
                spec_id=server_id,
                status="running",
                pid=proc.pid,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            self._save_state(new_state)
            return new_state

        except Exception as e:
            error_state = MCPServerState(
                spec_id=server_id,
                status="error",
                error_message=str(e),
            )
            self._save_state(error_state)
            return error_state

    def stop(self, server_id: str) -> MCPServerState:
        """Stop an MCP server, waiting for the PID to actually exit.

        Returns a state with ``status="stopped"`` once the PID is gone, or
        ``status="error"`` with ``error_message`` populated if the process
        refused to die within the timeout even after SIGKILL.
        """
        state = self._load_state(server_id)
        pid = state.pid if state else None

        if pid is None or not _pid_alive(pid):
            stopped = MCPServerState(spec_id=server_id, status="stopped")
            self._save_state(stopped)
            return stopped

        # 1. SIGTERM (Windows: this is already TerminateProcess).
        with contextlib.suppress(ProcessLookupError, OSError):
            os.kill(pid, signal.SIGTERM)

        if _wait_for_pid_dead(pid, self._stop_timeout):
            stopped = MCPServerState(spec_id=server_id, status="stopped")
            self._save_state(stopped)
            return stopped

        # 2. POSIX escalation: SIGKILL. (On Windows _SIGKILL aliases SIGTERM
        # but TerminateProcess was already called above, so this is a no-op
        # second attempt that won't loop forever.)
        with contextlib.suppress(ProcessLookupError, OSError):
            os.kill(pid, _SIGKILL)

        if _wait_for_pid_dead(pid, self._stop_timeout):
            stopped = MCPServerState(spec_id=server_id, status="stopped")
            self._save_state(stopped)
            return stopped

        err = MCPServerState(
            spec_id=server_id,
            status="error",
            pid=pid,
            error_message=(
                f"pid {pid} still alive after SIGTERM + SIGKILL "
                f"({self._stop_timeout}s each)"
            ),
        )
        self._save_state(err)
        return err

    def _build_env(self, spec: MCPServerSpec) -> dict[str, str]:
        env = os.environ.copy()
        for k, v in spec.env.items():
            if v.startswith("${") and v.endswith("}"):
                env_key = v[2:-1]
                env[k] = os.environ.get(env_key, "")
            else:
                env[k] = v
        return env

    def _save_state(self, state: MCPServerState) -> None:
        path = self._state_dir / f"{state.spec_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "spec_id": state.spec_id,
                    "status": state.status,
                    "pid": state.pid,
                    "port": state.port,
                    "started_at": state.started_at,
                    "last_health_check": state.last_health_check,
                    "error_message": state.error_message,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _delete_state(self, server_id: str) -> None:
        path = self._state_dir / f"{server_id}.json"
        with contextlib.suppress(FileNotFoundError):
            path.unlink()

    def _load_state(self, server_id: str) -> MCPServerState | None:
        path = self._state_dir / f"{server_id}.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return MCPServerState.model_validate(data)
