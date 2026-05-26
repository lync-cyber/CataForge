"""cataforge mcp — MCP server management."""

from __future__ import annotations

import click

from cataforge.cli.errors import CataforgeError, ConfigError
from cataforge.cli.guards import require_initialized
from cataforge.cli.helpers import emit_hint, resolve_root
from cataforge.cli.main import cli


@cli.group("mcp")
def mcp_group() -> None:
    """Manage MCP (Model Context Protocol) servers.

    Servers are declared in ``.cataforge/mcp/*.yaml`` specs. Use
    ``register`` to add a new one, ``start/stop`` to control its process,
    and ``list`` to see the current registry.
    """


@mcp_group.command("list")
@require_initialized
def mcp_list() -> None:
    """List all registered MCP servers."""
    from cataforge.mcp.registry import MCPRegistry

    registry = MCPRegistry(project_root=resolve_root())
    servers = registry.list_servers()
    if not servers:
        click.echo("No MCP servers registered.")
        emit_hint(
            "  Hint: register one with "
            "`cataforge mcp register <path/to/server.yaml>`."
        )
        return
    for srv in servers:
        click.echo(f"  {srv.id}: {srv.name} [{srv.transport}] — {srv.description}")


@mcp_group.command("register")
@click.argument("spec_path", type=click.Path(exists=True))
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite an existing spec at .cataforge/mcp/<id>.yaml.",
)
@require_initialized
def mcp_register(spec_path: str, force: bool) -> None:
    """Register an MCP server from a YAML spec file.

    The spec is copied to ``.cataforge/mcp/<id>.yaml`` so subsequent CLI
    runs (a separate process from this one) can find it.
    """
    from cataforge.mcp.registry import MCPRegistry

    try:
        registry = MCPRegistry(project_root=resolve_root())
        server = registry.register_from_file(spec_path, overwrite=force)
    except FileExistsError as e:
        raise ConfigError(str(e)) from None
    except Exception as e:
        raise ConfigError(f"Registration failed: {e}") from None
    click.echo(f"Registered: {server.id} ({server.name})")


@mcp_group.command("start")
@click.argument("server_id")
@require_initialized
def mcp_start(server_id: str) -> None:
    """Start an MCP server process."""
    from cataforge.mcp.lifecycle import MCPLifecycleManager

    try:
        mgr = MCPLifecycleManager(project_root=resolve_root())
        state = mgr.start(server_id)
    except ValueError as e:
        raise ConfigError(str(e)) from None

    if state.status == "running":
        click.echo(f"Started: {server_id} (pid={state.pid})")
        return
    raise CataforgeError(f"Failed to start: {state.error_message}")


@mcp_group.command("stop")
@click.argument("server_id")
@require_initialized
def mcp_stop(server_id: str) -> None:
    """Stop a running MCP server."""
    from cataforge.mcp.lifecycle import MCPLifecycleManager

    mgr = MCPLifecycleManager(project_root=resolve_root())
    state = mgr.stop(server_id)
    click.echo(f"Stopped: {server_id} (status={state.status})")


@mcp_group.command("health")
@click.argument("server_id")
@require_initialized
def mcp_health(server_id: str) -> None:
    """Probe a registered MCP server and report health.

    Dispatch follows the spec's ``health_check.type`` (``http`` / ``tcp`` /
    ``command``). When no ``health_check`` is declared, falls back to a
    pid-alive check using the persisted state. The probe outcome is also
    written to ``last_health_check`` for the next ``cataforge mcp list``.
    """
    from cataforge.mcp.lifecycle import MCPLifecycleManager

    mgr = MCPLifecycleManager(project_root=resolve_root())
    state = mgr.health(server_id)
    if state is None:
        raise ConfigError(f"Unknown MCP server: {server_id}")
    click.echo(f"Server : {server_id}")
    click.echo(f"Status : {state.status}")
    click.echo(f"Health : {state.last_health_check or '(no probe yet)'}")
    if state.status == "unhealthy":
        ctx = click.get_current_context()
        ctx.exit(1)
