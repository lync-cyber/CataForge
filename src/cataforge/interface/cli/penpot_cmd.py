"""cataforge penpot — Penpot integration management.

All subcommands delegate to ``cataforge.adapter.integrations.penpot`` and
translate its integer return code into either normal completion (0) or
a :class:`CataforgeError` carrying the same exit code. ``ensure_utf8``
is *not* called per-subcommand — ``cataforge.interface.cli.main`` already did that
once at startup.
"""

from __future__ import annotations

from cataforge.core.errors import CataforgeError
from cataforge.interface.cli.main import cli


def _run_penpot(command: str) -> None:
    """Load the penpot integration lazily and forward its exit code.

    ``command`` is the user-facing subcommand name (``"init"`` /
    ``"deploy"`` / ``"ensure"`` / …). Looks it up in
    ``penpot.HANDLERS``; missing entry surfaces a typed CataforgeError
    on stderr instead of the older ``getattr`` path's AttributeError.
    """
    from cataforge.adapter.integrations import penpot

    handler = penpot.HANDLERS.get(command)
    if handler is None:
        raise CataforgeError(
            f"unknown penpot subcommand {command!r}; registered: {sorted(penpot.HANDLERS)}"
        )

    penpot.load_dotenv(set_env=True)
    code = handler(penpot.get_config())
    if code == 0:
        return
    err = CataforgeError(f"`cataforge penpot {command}` failed (exit code {code}).")
    err.exit_code = code
    raise err


@cli.group("penpot")
def penpot_group() -> None:
    """Penpot 设计工具集成 — 给 LLM 提供读写设计稿的能力。

    \b
    三种模式（选一个）：
      cataforge penpot init       交互式向导（推荐首次使用）
      cataforge penpot remote     SaaS：design.penpot.app + 本地 MCP（零 Docker）
      cataforge penpot deploy     自托管：6 容器 + MCP（需 Docker）
      cataforge penpot mcp-only   只起 MCP，自己接已有 Penpot

    \b
    日常管理：
      cataforge penpot status     看运行状态
      cataforge penpot start      启动已配置的服务
      cataforge penpot stop       全部停止
      cataforge penpot doctor     诊断已知失败模式并给出修复建议
      cataforge penpot ensure     若 MCP 未运行则启动（skill 内部调度用）

    \b
    环境变量覆盖：
      PENPOT_PORT, PENPOT_MCP_SERVER_PORT, PENPOT_MCP_PLUGIN_PORT
      PENPOT_MCP_VERSION   pin @penpot/mcp 包版本（默认 latest）
      PENPOT_INSTALL_DIR   docker-compose.yml 落盘位置
    """


@penpot_group.command("init")
def penpot_init() -> None:
    """Interactive wizard: pick Remote / Local / MCP-only and configure."""
    _run_penpot("init")


@penpot_group.command("deploy")
def penpot_deploy() -> None:
    """Full deployment: Penpot (Docker stack) + MCP server."""
    _run_penpot("deploy")


@penpot_group.command("mcp-only")
def penpot_mcp_only() -> None:
    """Start only the MCP server (assumes Penpot is already running)."""
    _run_penpot("mcp-only")


@penpot_group.command("remote")
def penpot_remote() -> None:
    """SaaS mode: use design.penpot.app + a local MCP server (no Docker).

    Spins up the MCP server on localhost and prints browser-side steps to
    load the MCP plugin into design.penpot.app. The fastest path for users
    who don't need a self-hosted Penpot instance.
    """
    _run_penpot("remote")


@penpot_group.command("start")
def penpot_start() -> None:
    """Start previously deployed Penpot services."""
    _run_penpot("start")


@penpot_group.command("stop")
def penpot_stop() -> None:
    """Stop all running Penpot services."""
    _run_penpot("stop")


@penpot_group.command("status")
def penpot_status() -> None:
    """Show the status of Penpot services and the MCP server."""
    _run_penpot("status")


@penpot_group.command("doctor")
def penpot_doctor() -> None:
    """Diagnose Penpot integration failures and suggest fixes.

    Checks Node version, compose template freshness (Bug 1 fix presence),
    and the MCP log tail for known error patterns (Bug 2 / port-in-use /
    nginx upstream).
    """
    _run_penpot("doctor")


@penpot_group.command("ensure")
def penpot_ensure() -> None:
    """Idempotent: bring the Penpot MCP server up if it isn't already.

    Used by the Penpot skills (penpot-sync / penpot-implement /
    penpot-review) when they detect no Penpot MCP tools in the runtime
    tool list — they call ``cataforge penpot ensure`` to attempt a
    start-up before falling back to ``blocked``.
    """
    _run_penpot("ensure")
