"""cataforge penpot — Penpot integration management.

All subcommands delegate to ``cataforge.integrations.penpot`` and
translate its integer return code into either normal completion (0) or
a :class:`CataforgeError` carrying the same exit code. ``ensure_utf8_stdio``
is *not* called per-subcommand — ``cataforge.cli.main`` already did that
once at startup.
"""

from __future__ import annotations

from cataforge.cli.errors import CataforgeError
from cataforge.cli.main import cli


def _run_penpot(handler_name: str, command_label: str) -> None:
    """Load the penpot integration lazily and forward its exit code."""
    from cataforge.integrations import penpot

    load_dotenv = penpot.load_dotenv
    get_config = penpot._get_config
    handler = getattr(penpot, handler_name)

    load_dotenv(set_env=True)
    code = handler(get_config())
    if code == 0:
        return
    err = CataforgeError(f"`cataforge penpot {command_label}` failed (exit code {code}).")
    err.exit_code = code
    raise err


@cli.group("penpot")
def penpot_group() -> None:
    """Manage Penpot Docker deployment and the Penpot MCP server.

    Reads ``.cataforge/integrations/penpot.env`` for credentials and
    ports. Requires Docker to be running on PATH.
    """


@penpot_group.command("deploy")
def penpot_deploy() -> None:
    """Full deployment: Penpot (Docker stack) + MCP server."""
    _run_penpot("cmd_deploy", "deploy")


@penpot_group.command("mcp-only")
def penpot_mcp_only() -> None:
    """Start only the MCP server (assumes Penpot is already running)."""
    _run_penpot("cmd_mcp_only", "mcp-only")


@penpot_group.command("start")
def penpot_start() -> None:
    """Start previously deployed Penpot services."""
    _run_penpot("cmd_start", "start")


@penpot_group.command("stop")
def penpot_stop() -> None:
    """Stop all running Penpot services."""
    _run_penpot("cmd_stop", "stop")


@penpot_group.command("status")
def penpot_status() -> None:
    """Show the status of Penpot services and the MCP server."""
    _run_penpot("cmd_status", "status")
