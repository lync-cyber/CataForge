"""MCP server lifecycle management — start, stop, health, persisted state.

Crash recovery and cross-process correctness:

* ``start()`` first reads the persisted JSON state from ``.cataforge/.mcp-
  state/<id>.json`` and verifies the recorded PID is actually alive (cross-
  platform check). A stale "running" state from a previous CLI invocation
  whose process has since died is cleaned up so the next start succeeds
  instead of silently refusing. After spawn, a readiness probe runs the
  configured ``health_check`` so the start return value reflects whether
  the server is actually responsive, not just whether the OS forked.
* ``stop()`` sends SIGTERM, waits for the PID to disappear (up to
  ``stop_timeout_seconds``), then escalates to SIGKILL on POSIX (Windows
  SIGTERM already maps to ``TerminateProcess``, which is forceful). The
  final state records ``stopped`` only after the PID is confirmed gone.
* ``health()`` dispatches by ``spec.health_check.type`` — HTTP GET, TCP
  socket connect, or a command exit code — and persists the result on
  ``state.last_health_check``. When no ``health_check`` is declared in the
  spec, falls back to ``pid_alive`` so callers always get an answer.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.core.schema.mcp_spec import MCPServerSpec, MCPServerState
from cataforge.runtime.mcp.health_probe import probe as _health_probe
from cataforge.runtime.mcp.registry import MCPRegistry
from cataforge.runtime.mcp.state_store import delete_state, load_state, save_state
from cataforge.utils.process import _wait_for_pid_dead, pid_alive

logger = logging.getLogger("cataforge.runtime.mcp.lifecycle")

DEFAULT_STOP_TIMEOUT_SECONDS = 5.0
_PID_POLL_INTERVAL_SECONDS = 0.1
# Windows has no SIGKILL — SIGTERM there is already TerminateProcess.
_SIGKILL = getattr(signal, "SIGKILL", signal.SIGTERM)

_SPAWN_LOCK_TIMEOUT_SECONDS_DEFAULT = 10.0
_SPAWN_LOCK_POLL_INTERVAL_SECONDS = 0.05

# In-process serialization for the spawn-lock — a layer above the file-based
# lock that protects against same-process thread contention.  Why both: the
# file lock alone hits a Windows + Py 3.10 race where ``os.open(O_EXCL)``
# from a second thread keeps reporting ``FileExistsError`` long after the
# holder thread's ``unlink`` returned success (and after the dirent is gone
# to ``os.path.exists``). Symptom: ``test_concurrent_start_produces_single_pid``
# starves and trips the 10s timeout even though the holder finished in 15ms.
# A ``threading.Lock`` keyed by lock path keeps two threads from ever needing
# the file lock to mediate between themselves; the file lock retains its role
# for cross-process contention.
_INPROC_LOCKS: dict[str, threading.Lock] = {}
_INPROC_LOCKS_GUARD = threading.Lock()


def _inproc_lock(lock_path: Path) -> threading.Lock:
    """Per-lock-path threading.Lock, lazily instantiated."""
    key = str(lock_path)
    with _INPROC_LOCKS_GUARD:
        lock = _INPROC_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _INPROC_LOCKS[key] = lock
        return lock


def _spawn_lock_timeout() -> float:
    """Per-call timeout in seconds. ``CATAFORGE_MCP_SPAWN_LOCK_TIMEOUT``
    overrides the 10s default — set to ``30`` on slow Windows CI where
    Python interpreter spawn alone burns 1-2s per process and two
    contending threads can otherwise exhaust the budget."""
    raw = os.environ.get("CATAFORGE_MCP_SPAWN_LOCK_TIMEOUT", "")
    if raw:
        try:
            return max(1.0, float(raw))
        except ValueError:
            pass
    return _SPAWN_LOCK_TIMEOUT_SECONDS_DEFAULT


@contextlib.contextmanager
def _spawn_lock(lock_path: Path):
    """Serialize MCP server spawn across threads and processes.

    Uses ``os.open(..., O_CREAT | O_EXCL)`` as a portable atomic flag —
    avoids the platform split between ``fcntl.flock`` and
    ``msvcrt.locking``. Stale locks (holder PID dead) are recovered;
    no SIGKILL-mid-spawn footgun.
    """
    timeout = _spawn_lock_timeout()
    deadline = time.monotonic() + timeout
    # Same-process serialization first. Two peer threads inside one Python
    # process never race for the file lock — only cross-process callers do.
    inproc = _inproc_lock(lock_path)
    inproc.acquire()
    try:
        acquired = False
        while time.monotonic() < deadline:
            try:
                fd = os.open(
                    str(lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                try:
                    os.write(fd, str(os.getpid()).encode("ascii"))
                finally:
                    os.close(fd)
                acquired = True
                break
            except FileExistsError:
                lock_pid: int | None = None
                with contextlib.suppress(OSError, ValueError):
                    lock_pid = int(lock_path.read_text(encoding="ascii").strip())
                if lock_pid is not None and not pid_alive(lock_pid):
                    with contextlib.suppress(OSError):
                        os.unlink(str(lock_path))
                    continue
                time.sleep(_SPAWN_LOCK_POLL_INTERVAL_SECONDS)
        if not acquired:
            raise TimeoutError(f"could not acquire MCP spawn lock {lock_path} within {timeout}s")
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                os.unlink(str(lock_path))
    finally:
        inproc.release()


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
        """Start an MCP server, honouring persisted state across CLI runs.

        The spawn lock only guards the *spawn-or-attach* decision plus
        the state write that publishes the new PID. Once that state is on
        disk a concurrent caller can re-read it, see ``status=running``
        with a live PID, and return without re-entering the spawn path —
        so we don't need the lock to cover the readiness probe.  Holding
        the lock through ``self.health()`` would otherwise extend the
        critical section by seconds on Windows CI (Python startup +
        socket / HTTP probes) and starve peer threads to timeout.
        """
        spec = self._registry.get_server(server_id)
        if spec is None:
            raise ValueError(f"Unknown MCP server: {server_id}")

        self._state_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._state_dir / f"{server_id}.spawn.lock"

        new_state: MCPServerState | None = None
        with _spawn_lock(lock_path):
            # Re-check after acquiring the lock — a peer caller may have
            # spawned while we were waiting, and the persisted state
            # below is the only proof we have.
            persisted = self._load_state(server_id)
            if persisted and persisted.status == "running":
                if pid_alive(persisted.pid):
                    return persisted
                logger.info(
                    "MCP %s: stale 'running' state (pid=%s) — process gone, restarting",
                    server_id,
                    persisted.pid,
                )
                self._delete_state(server_id)

            try:
                cmd = [spec.command] + spec.args
                env = self._build_env(spec)

                if os.environ.get("CATAFORGE_MCP_DEBUG") == "1":
                    stderr_target: int | None = None
                else:
                    stderr_target = subprocess.DEVNULL

                proc = subprocess.Popen(  # allow-raw-subprocess: long-running MCP server
                    cmd,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr_target,
                    cwd=str(self._paths.root),
                )

                new_state = MCPServerState(
                    spec_id=server_id,
                    status="running",
                    pid=proc.pid,
                    started_at=datetime.now(UTC).isoformat(),
                )
                self._save_state(new_state)
            except Exception as e:
                error_state = MCPServerState(
                    spec_id=server_id,
                    status="error",
                    error_message=str(e),
                )
                self._save_state(error_state)
                return error_state

        # Lock released. Readiness probe outside so peer callers waiting
        # for the lock can proceed (and will short-circuit on the live
        # persisted state we just wrote).
        if new_state is None:  # defensive — should never happen
            return MCPServerState(
                spec_id=server_id, status="error", error_message="spawn produced no state"
            )

        with contextlib.suppress(Exception):
            refreshed = self.health(server_id)
            if refreshed is not None:
                return refreshed
        return new_state

    def stop(self, server_id: str) -> MCPServerState:
        """Stop an MCP server, waiting for the PID to actually exit.

        Returns a state with ``status="stopped"`` once the PID is gone, or
        ``status="error"`` with ``error_message`` populated if the process
        refused to die within the timeout even after SIGKILL.
        """
        state = self._load_state(server_id)
        pid = state.pid if state else None

        if pid is None or not pid_alive(pid):
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
                f"pid {pid} still alive after SIGTERM + SIGKILL ({self._stop_timeout}s each)"
            ),
        )
        self._save_state(err)
        return err

    def health(self, server_id: str) -> MCPServerState | None:
        """Probe the server and persist the result on ``last_health_check``.

        Dispatch is by ``spec.health_check.type``:

        * ``http`` — ``GET`` ``health_check.target`` with the configured
          timeout. Healthy iff the HTTP status is 2xx.
        * ``tcp`` — open a socket to ``"host:port"`` parsed from
          ``health_check.target``. Healthy iff the connect succeeds.
        * ``command`` — run ``health_check.target`` (must be a ``list[str]``)
          without a shell with the configured timeout. Healthy iff exit code is 0.

        When no ``health_check`` is declared, falls back to a pid-alive
        probe so callers always get an answer.

        Returns ``None`` only when the server is unknown to the registry.
        """
        spec = self._registry.get_server(server_id)
        if spec is None:
            return None

        state = self._load_state(server_id) or MCPServerState(spec_id=server_id)
        result = _health_probe(spec, state.pid)

        new_status = state.status
        if state.status == "running" and result.status == "unhealthy":
            new_status = "unhealthy"
        elif state.status == "unhealthy" and result.status == "healthy":
            new_status = "running"
        refreshed = MCPServerState(
            spec_id=server_id,
            status=new_status,
            pid=state.pid,
            port=state.port,
            started_at=state.started_at,
            last_health_check=f"{result.ts}|{result.status}|{result.detail}",
            error_message=state.error_message,
        )
        self._save_state(refreshed)
        return refreshed

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
        save_state(self._state_dir, state)

    def _delete_state(self, server_id: str) -> None:
        delete_state(self._state_dir, server_id)

    def _load_state(self, server_id: str) -> MCPServerState | None:
        return load_state(self._state_dir, server_id)
