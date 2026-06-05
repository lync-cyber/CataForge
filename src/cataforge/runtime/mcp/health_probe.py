"""MCP server health probe — HTTP, TCP, and command-exit strategies."""

from __future__ import annotations

import socket
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from cataforge.core.schema.mcp_spec import HealthCheckSpec, MCPServerSpec
from cataforge.utils.process import pid_alive
from cataforge.utils.run_subprocess import run as run_proc

HealthStatus = Literal["healthy", "unhealthy", "unknown"]


@dataclass(frozen=True)
class HealthResult:
    """Outcome of a single health probe.

    ``status`` is the bottom-line verdict; ``detail`` carries the
    human-readable reason (HTTP status code, socket error, command exit
    line) so CLI output and EVENT-LOG entries can explain *why*. ``ts``
    is the ISO-8601 UTC timestamp written back to
    :attr:`MCPServerState.last_health_check`.
    """

    status: HealthStatus
    detail: str
    ts: str


def probe(spec: MCPServerSpec, pid: int | None) -> HealthResult:
    """Run the configured probe for *spec* and return a structured result.

    When no ``health_check`` is declared falls back to a :func:`pid_alive`
    check so callers always get an answer. *pid* is only used for that
    fallback path.
    """
    ts = datetime.now(UTC).isoformat()
    check = spec.health_check
    if check is None:
        alive = pid_alive(pid)
        return HealthResult(
            status="healthy" if alive else "unhealthy",
            detail=f"pid_alive={alive} (pid={pid})",
            ts=ts,
        )

    if check.type == "http":
        return _probe_http(check, ts)
    if check.type == "tcp":
        return _probe_tcp(check, ts)
    if check.type == "command":
        return _probe_command(check, ts)
    return HealthResult(
        status="unknown",
        detail=f"unsupported health_check.type={check.type!r}",
        ts=ts,
    )


def _probe_http(check: HealthCheckSpec, ts: str) -> HealthResult:
    import urllib.error
    import urllib.request

    target = check.target
    if not isinstance(target, str) or not target:
        return HealthResult(status="unknown", detail="http: target must be a URL string", ts=ts)
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
        return HealthResult(status="unhealthy", detail=f"http: {exc}", ts=ts)
    return HealthResult(
        status="healthy" if 200 <= code < 300 else "unhealthy",
        detail=f"http: HTTP {code}",
        ts=ts,
    )


def _probe_tcp(check: HealthCheckSpec, ts: str) -> HealthResult:
    target = check.target
    if not isinstance(target, str) or ":" not in target:
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
        with socket.create_connection((host, port), timeout=check.timeout_seconds):
            pass
    except OSError as exc:
        return HealthResult(status="unhealthy", detail=f"tcp: {exc}", ts=ts)
    return HealthResult(status="healthy", detail=f"tcp: connected to {host}:{port}", ts=ts)


def _probe_command(check: HealthCheckSpec, ts: str) -> HealthResult:
    target = check.target
    if not target:
        return HealthResult(status="unknown", detail="command: target is empty", ts=ts)
    if isinstance(target, str):
        return HealthResult(
            status="unknown",
            detail=(f"command: health_check.target must be a list of args; got string {target!r}"),
            ts=ts,
        )
    try:
        proc = run_proc(target, timeout=check.timeout_seconds)
    except subprocess.TimeoutExpired:
        return HealthResult(
            status="unhealthy",
            detail=f"command: timed out after {check.timeout_seconds}s",
            ts=ts,
        )
    except OSError as exc:
        return HealthResult(status="unhealthy", detail=f"command: {exc}", ts=ts)
    if proc.returncode == 0:
        return HealthResult(status="healthy", detail="command: exit 0", ts=ts)
    return HealthResult(
        status="unhealthy",
        detail=f"command: exit {proc.returncode}",
        ts=ts,
    )
