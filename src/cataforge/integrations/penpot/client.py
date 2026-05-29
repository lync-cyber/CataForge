"""Claude Code MCP registration for the Penpot server."""

from __future__ import annotations

import subprocess

from cataforge.utils.common import (
    BOLD,
    NC,
    has_command,
    info,
    ok,
    run_cmd,
    section,
    warn,
)


def _run_claude_mcp(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    """Run ``claude mcp …`` best-effort; return None if it hangs or is absent.

    ``claude mcp list`` health-checks every registered MCP server serially,
    so on a machine with several slow remote servers it routinely exceeds a
    short budget. A hung claude CLI must not abort an already-started Penpot
    MCP — registration is convenience, not a precondition.
    """
    try:
        return run_cmd(["claude", *args], timeout=30)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def register_claude_mcp(config: dict) -> None:
    section("注册 MCP 到 Claude Code")
    mcp_url = f"http://localhost:{config['mcp_port']}/mcp"
    manual_hint = f"claude mcp add penpot -t http {mcp_url}"
    if not has_command("claude"):
        info(f"Claude Code CLI 未检测到，请手动注册:\n    {BOLD}{manual_hint}{NC}")
        return
    listed = _run_claude_mcp(["mcp", "list"])
    if (
        listed is not None
        and listed.returncode == 0
        and listed.stdout
        and "penpot" in listed.stdout.lower()
    ):
        ok("Claude Code 已注册 penpot MCP")
        return
    added = _run_claude_mcp(["mcp", "add", "penpot", "-t", "http", mcp_url])
    if added is None:
        warn(f"claude CLI 无响应，请手动注册: {manual_hint}")
        return
    stdout = added.stdout or ""
    if added.returncode == 0 or "Added" in stdout or "already" in stdout:
        ok("已注册到 Claude Code")
    else:
        warn(f"自动注册失败，请手动执行: {manual_hint}")
