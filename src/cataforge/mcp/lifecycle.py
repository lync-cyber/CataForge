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
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.mcp.registry import MCPRegistry
from cataforge.schema.mcp_spec import HealthCheckSpec, MCPServerSpec, MCPServerState

logger = logging.getLogger("cataforge.mcp.lifecycle")

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
                if lock_pid is not None and not _pid_alive(lock_pid):
                    with contextlib.suppress(OSError):
                        os.unlink(str(lock_path))
                    continue
                time.sleep(_SPAWN_LOCK_POLL_INTERVAL_SECONDS)
        if not acquired:
            raise TimeoutError(
                f"could not acquire MCP spawn lock {lock_path} within "
                f"{timeout}s"
            )
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                os.unlink(str(lock_path))
    finally:
        inproc.release()

HealthStatus = Literal["healthy", "unhealthy", "unknown"]


@dataclass(frozen=True)
class HealthResult:
    """Outcome of a single ``health()`` probe.

    ``status`` is the bottom-line verdict; ``detail`` carries the
    human-readable reason (HTTP status code, socket error, command exit
    line) so CLI output and EVENT-LOG entries can explain *why*. ``ts``
    is the ISO-8601 UTC timestamp written back to
    :attr:`MCPServerState.last_health_check`.
    """

    status: HealthStatus
    detail: str
    ts: str


def _pid_alive(pid: int | None) -> bool:
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
                if _pid_alive(persisted.pid):
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

                proc = subprocess.Popen(
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
                    started_at=datetime.now(timezone.utc).isoformat(),
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
            return MCPServerState(spec_id=server_id, status="error",
                                  error_message="spawn produced no state")

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

        result = self._probe(spec)

        state = self._load_state(server_id) or MCPServerState(spec_id=server_id)
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

    def _probe(self, spec: MCPServerSpec) -> HealthResult:
        """Run the configured probe and return a structured result."""
        ts = datetime.now(timezone.utc).isoformat()
        check = spec.health_check
        if check is None:
            state = self._load_state(spec.id)
            pid = state.pid if state else None
            alive = _pid_alive(pid)
            return HealthResult(
                status="healthy" if alive else "unhealthy",
                detail=f"pid_alive={alive} (pid={pid})",
                ts=ts,
            )

        if check.type == "http":
            return self._probe_http(check, ts)
        if check.type == "tcp":
            return self._probe_tcp(check, ts)
        if check.type == "command":
            return self._probe_command(check, ts)
        return HealthResult(
            status="unknown",
            detail=f"unsupported health_check.type={check.type!r}",
            ts=ts,
        )

    @staticmethod
    def _probe_http(check: HealthCheckSpec, ts: str) -> HealthResult:
        target = check.target
        if not target:
            return HealthResult(
                status="unknown", detail="http: target is empty", ts=ts
            )
        req = urllib.request.Request(target, method="GET")
        try:
            with urllib.request.urlopen(  # noqa: S310 — operator-configured URL
                req, timeout=check.timeout_seconds
            ) as resp:
                code = int(resp.status)
        except urllib.error.HTTPError as exc:
            return HealthResult(
                status="unhealthy",
                detail=f"http: HTTP {exc.code}",
                ts=ts,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return HealthResult(
                status="unhealthy", detail=f"http: {exc}", ts=ts
            )
        return HealthResult(
            status="healthy" if 200 <= code < 300 else "unhealthy",
            detail=f"http: HTTP {code}",
            ts=ts,
        )

    @staticmethod
    def _probe_tcp(check: HealthCheckSpec, ts: str) -> HealthResult:
        target = check.target
        if ":" not in target:
            return HealthResult(
                status="unknown",
                detail=f"tcp: target {target!r} must be 'host:port'",
                ts=ts,
            )
        host, _, port_str = target.rpartition(":")
        try:
            port = int(port_str)
        except ValueError:
            return HealthResult(
                status="unknown",
                detail=f"tcp: port {port_str!r} is not an integer",
                ts=ts,
            )
        try:
            with socket.create_connection(
                (host, port), timeout=check.timeout_seconds
            ):
                pass
        except OSError as exc:
            return HealthResult(
                status="unhealthy", detail=f"tcp: {exc}", ts=ts
            )
        return HealthResult(
            status="healthy", detail=f"tcp: connected to {host}:{port}", ts=ts
        )

    @staticmethod
    def _probe_command(check: HealthCheckSpec, ts: str) -> HealthResult:
        target = check.target
        if not target:
            return HealthResult(
                status="unknown", detail="command: target is empty", ts=ts
            )
        if isinstance(target, str):
            return HealthResult(
                status="unknown",
                detail=(
                    f"command: health_check.target must be a list of args;"
                    f" got string {target!r}"
                ),
                ts=ts,
            )
        try:
            proc = subprocess.run(  # noqa: S603
                target,
                shell=False,
                timeout=check.timeout_seconds,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired:
            return HealthResult(
                status="unhealthy",
                detail=f"command: timed out after {check.timeout_seconds}s",
                ts=ts,
            )
        except OSError as exc:
            return HealthResult(
                status="unhealthy", detail=f"command: {exc}", ts=ts
            )
        if proc.returncode == 0:
            return HealthResult(
                status="healthy", detail="command: exit 0", ts=ts
            )
        return HealthResult(
            status="unhealthy",
            detail=f"command: exit {proc.returncode}",
            ts=ts,
        )

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
