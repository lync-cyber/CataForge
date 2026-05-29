"""Penpot MCP server process lifecycle (npx-spawned)."""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import time
import urllib.error
import urllib.request

from cataforge.core.errors import CataforgeError
from cataforge.integrations.penpot._constants import (
    DEFAULT_MCP_PACKAGE_VERSION,
    MCP_HEALTH_TIMEOUT,
    MCP_LOG_FILE,
    MCP_PID_FILE,
    PLATFORM,
)
from cataforge.mcp.lifecycle import pid_alive
from cataforge.utils.common import (
    BOLD,
    DIM,
    NC,
    YELLOW,
    fail,
    find_available_port,
    info,
    ok,
    section,
    warn,
)
from cataforge.utils.run_subprocess import run as run_proc


def _read_mcp_pid() -> int | None:
    if not os.path.isfile(MCP_PID_FILE):
        return None
    try:
        with open(MCP_PID_FILE, encoding="utf-8") as f:
            return int(f.read().strip())
    except (ValueError, OSError):
        return None


def _write_mcp_pid(pid: int) -> None:
    with open(MCP_PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(pid))


def _remove_mcp_pid() -> None:
    with contextlib.suppress(OSError):
        os.remove(MCP_PID_FILE)


def _is_mcp_running(config: dict) -> bool:
    try:
        req = urllib.request.Request(f"http://localhost:{config['mcp_port']}/mcp", method="GET")
        # 2s is deliberate: this probe runs on every `penpot status` /
        # `penpot ensure` / Penpot skill warm-up and must fail-fast on
        # "server not up" without making the user wait. A higher
        # timeout would make those entry points feel hung when MCP
        # isn't installed yet — the failure mode we're checking for.
        # Do NOT raise without a corresponding adjustment in
        # ``cmd_ensure`` / ``cmd_status`` UX.
        urllib.request.urlopen(req, timeout=2)
        return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _mcp_npx_env(config: dict) -> dict[str, str]:
    """Environment for the npx-spawned @penpot/mcp process.

    PNPM_CONFIG_STRICT_DEP_BUILDS=false demotes ERR_PNPM_IGNORED_BUILDS (raised
    by pnpm 10+ when esbuild/sharp's build scripts are not pre-approved) into
    a warning so the monorepo install can finish.
    """
    env = os.environ.copy()
    env["PORT"] = str(config["mcp_port"])
    env["PLUGIN_PORT"] = str(config["plugin_port"])
    env["PNPM_CONFIG_STRICT_DEP_BUILDS"] = "false"
    env["npm_config_strict_dep_builds"] = "false"
    env["COREPACK_ENABLE_DOWNLOAD_PROMPT"] = "0"
    return env


def start_mcp(config: dict) -> bool:
    section("启动 MCP Server")
    if _is_mcp_running(config):
        ok(f"MCP Server 已在端口 {config['mcp_port']} 运行")
        return True
    config["mcp_port"] = find_available_port(config["mcp_port"], "MCP Server")
    config["plugin_port"] = find_available_port(config["plugin_port"], "Plugin Server")
    env = _mcp_npx_env(config)
    mcp_version = config.get("mcp_version") or DEFAULT_MCP_PACKAGE_VERSION
    package_spec = f"@penpot/mcp@{mcp_version}"
    info(f"通过 npx {package_spec} 启动 MCP Server...")
    # Resolve npx to full path so we can avoid shell=True on Windows
    # (npx is typically `npx.cmd`, which Popen otherwise can't locate without the shell).
    npx_path = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx_path:
        fail("未找到 npx 命令，请先安装 Node.js")
        return False
    cmd = [npx_path, "--yes", package_spec]
    with open(MCP_LOG_FILE, "wb") as log_fh:
        if PLATFORM == "windows":
            proc = subprocess.Popen(  # allow-raw-subprocess: long-running MCP server
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            proc = subprocess.Popen(  # allow-raw-subprocess: long-running MCP server
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
    _write_mcp_pid(proc.pid)
    info(f"等待 MCP Server 就绪 (最多 {MCP_HEALTH_TIMEOUT}s)...")
    for _i in range(MCP_HEALTH_TIMEOUT):
        if _is_mcp_running(config):
            ok(f"MCP Server 就绪 {DIM}-> http://localhost:{config['mcp_port']}/mcp{NC}")
            return True
        if proc.poll() is not None:
            _report_mcp_failure(proc.returncode)
            _remove_mcp_pid()
            return False
        time.sleep(1)
    warn(f"MCP Server 在 {MCP_HEALTH_TIMEOUT}s 内未就绪")
    return False


def _report_mcp_failure(exit_code: int | None) -> None:
    """Print a tail of the MCP log plus a diagnosis for common failure modes."""
    fail(f"MCP Server 进程已退出 (exit={exit_code})")
    tail = _tail_log(MCP_LOG_FILE, lines=20)
    if tail:
        print(f"\n  {DIM}日志尾段 ({MCP_LOG_FILE}):{NC}")
        for line in tail:
            print(f"    {DIM}{line}{NC}")
    diagnosis = _diagnose_mcp_log("\n".join(tail))
    if diagnosis:
        print()
        for line in diagnosis:
            print(f"  {line}")


def _tail_log(path: str, *, lines: int = 20) -> list[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            buf = f.readlines()
    except OSError:
        return []
    return [line.rstrip("\r\n") for line in buf[-lines:]]


def _diagnose_mcp_log(text: str) -> list[str]:
    """Return human-readable hints for known MCP startup failures.

    Backed by :mod:`cataforge.cli.diagnostics` so adding/editing a pattern
    updates both ``penpot start`` failure reports and ``penpot doctor``
    at the same time. Returns a flat list of strings to stay backward-
    compatible with the prior signature (callers use ``"\\n".join`` for
    log-style assertions).
    """
    from cataforge.cli.diagnostics import PENPOT_PATTERNS
    from cataforge.cli.ui import _pattern_matches

    hints: list[str] = []
    for p in PENPOT_PATTERNS:
        if not _pattern_matches(p.needle, text):
            continue
        hints.append(f"{YELLOW}诊断{NC}: {p.diagnosis}")
        fix_line = f"{YELLOW}修复{NC}: {p.fix_action}"
        if p.fix_command:
            fix_line += f"\n         → {BOLD}{p.fix_command}{NC}"
        hints.append(fix_line)
        # Only report the first matching pattern to avoid noise — the
        # original implementation used elif/elif so callers depend on this.
        break
    return hints


def stop_mcp(config: dict) -> bool:
    pid = _read_mcp_pid()
    if pid and pid_alive(pid):
        info(f"停止 MCP Server (PID: {pid})...")
        try:
            if PLATFORM == "windows":
                # taskkill is part of every supported Windows SKU but is
                # absent from stripped images (Nano Server, some CI
                # containers). Fail loudly rather than swallow the
                # FileNotFoundError into the bare ``except OSError``
                # below and leave the user looking at "stopped" output
                # with the process still alive.
                if not shutil.which("taskkill"):
                    raise CataforgeError(
                        "taskkill not found on PATH — required to stop the "
                        f"Penpot MCP server (PID {pid}) on Windows. Install "
                        "the Windows admin tools (taskkill ships with every "
                        "Pro/Enterprise SKU) or stop the process manually."
                    )
                run_proc(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    timeout=10,
                )
            else:
                os.kill(pid, signal.SIGTERM)
                for _ in range(10):
                    if not pid_alive(pid):
                        break
                    time.sleep(0.5)
                else:
                    os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        _remove_mcp_pid()
        ok("MCP Server 已停止")
        return True
    if _is_mcp_running(config):
        warn(f"端口 {config['mcp_port']} 仍有服务，但无 PID 记录")
        _remove_mcp_pid()
        return False
    info("MCP Server 未在运行")
    _remove_mcp_pid()
    return True
