"""Claude Code MCP registration for the Penpot server."""

from __future__ import annotations

import re
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

_SECRET_QUERY_PARAM = re.compile(r"((?:userToken|token|api[_-]?key)=)[^&\s]+", re.IGNORECASE)


def mask_url_secrets(url: str) -> str:
    """Mask token-like query params so a URL is safe to print to a terminal/log.

    Penpot's hosted Remote MCP carries its auth as ``?userToken=…`` in the URL,
    so display surfaces must redact it; the value passed to ``claude mcp add``
    keeps the real token.
    """
    return _SECRET_QUERY_PARAM.sub(r"\1***", url)


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


def register_claude_mcp(mcp_url: str) -> None:
    section("注册 MCP 到 Claude Code")
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
