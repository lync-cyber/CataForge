"""cataforge penpot — Penpot integration management."""

from __future__ import annotations

from cataforge.cli.main import cli


@cli.group("penpot")
def penpot_group() -> None:
    """Manage Penpot Docker deployment and MCP server."""


@penpot_group.command("deploy")
def penpot_deploy() -> None:
    """Full deployment: Penpot (Docker) + MCP Server."""
    from cataforge.integrations.penpot import (
        _get_config,
        cmd_deploy,
        ensure_utf8_stdio,
        load_dotenv,
    )

    ensure_utf8_stdio()
    load_dotenv(set_env=True)
    raise SystemExit(cmd_deploy(_get_config()))


@penpot_group.command("mcp-only")
def penpot_mcp_only() -> None:
    """Start MCP Server only (assumes Penpot is already running)."""
    from cataforge.integrations.penpot import (
        _get_config,
        cmd_mcp_only,
        ensure_utf8_stdio,
        load_dotenv,
    )

    ensure_utf8_stdio()
    load_dotenv(set_env=True)
    raise SystemExit(cmd_mcp_only(_get_config()))


@penpot_group.command("start")
def penpot_start() -> None:
    """Start previously deployed services."""
    from cataforge.integrations.penpot import _get_config, cmd_start, ensure_utf8_stdio, load_dotenv

    ensure_utf8_stdio()
    load_dotenv(set_env=True)
    raise SystemExit(cmd_start(_get_config()))


@penpot_group.command("stop")
def penpot_stop() -> None:
    """Stop all Penpot services."""
    from cataforge.integrations.penpot import _get_config, cmd_stop, ensure_utf8_stdio, load_dotenv

    ensure_utf8_stdio()
    load_dotenv(set_env=True)
    raise SystemExit(cmd_stop(_get_config()))


@penpot_group.command("status")
def penpot_status() -> None:
    """Show service status."""
    from cataforge.integrations.penpot import (
        _get_config,
        cmd_status,
        ensure_utf8_stdio,
        load_dotenv,
    )

    ensure_utf8_stdio()
    load_dotenv(set_env=True)
    raise SystemExit(cmd_status(_get_config()))
