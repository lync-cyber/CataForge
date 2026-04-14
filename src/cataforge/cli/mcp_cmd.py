"""cataforge mcp — MCP server management."""

from __future__ import annotations

import click

from cataforge.cli.main import cli


@cli.group("mcp")
def mcp_group() -> None:
    """Manage MCP (Model Context Protocol) servers."""


@mcp_group.command("list")
def mcp_list() -> None:
    """List all registered MCP servers."""
    from cataforge.mcp.registry import MCPRegistry

    registry = MCPRegistry()
    servers = registry.list_servers()
    if not servers:
        click.echo("No MCP servers registered.")
        return
    for srv in servers:
        click.echo(f"  {srv.id}: {srv.name} [{srv.transport}] — {srv.description}")


@mcp_group.command("register")
@click.argument("spec_path", type=click.Path(exists=True))
def mcp_register(spec_path: str) -> None:
    """Register an MCP server from a YAML spec file."""
    from cataforge.mcp.registry import MCPRegistry

    try:
        registry = MCPRegistry()
        server = registry.register_from_file(spec_path)
        click.echo(f"Registered: {server.id} ({server.name})")
    except Exception as e:
        click.secho(f"Registration failed: {e}", fg="red", err=True)
        raise SystemExit(1) from None


@mcp_group.command("start")
@click.argument("server_id")
def mcp_start(server_id: str) -> None:
    """Start an MCP server."""
    from cataforge.mcp.lifecycle import MCPLifecycleManager

    try:
        mgr = MCPLifecycleManager()
        state = mgr.start(server_id)
        if state.status == "running":
            click.echo(f"Started: {server_id} (pid={state.pid})")
        else:
            click.secho(f"Failed to start: {state.error_message}", fg="red", err=True)
            raise SystemExit(1)
    except ValueError as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        raise SystemExit(1) from None


@mcp_group.command("stop")
@click.argument("server_id")
def mcp_stop(server_id: str) -> None:
    """Stop an MCP server."""
    from cataforge.mcp.lifecycle import MCPLifecycleManager

    mgr = MCPLifecycleManager()
    state = mgr.stop(server_id)
    click.echo(f"Stopped: {server_id} (status={state.status})")
