"""cataforge agent — agent management."""

from __future__ import annotations

import click

from cataforge.cli.main import cli


@cli.group("agent")
def agent_group() -> None:
    """Manage CataForge agents."""


@agent_group.command("list")
def agent_list() -> None:
    """List all registered agents."""
    from cataforge.agent.manager import AgentManager

    mgr = AgentManager()
    agents = mgr.list_agents()
    if not agents:
        click.echo("No agents found.")
        return
    for a in agents:
        click.echo(f"  {a}")


@agent_group.command("validate")
@click.argument("agent_id", required=False)
def agent_validate(agent_id: str | None) -> None:
    """Validate agent definitions."""
    from cataforge.agent.manager import AgentManager

    mgr = AgentManager()
    issues = mgr.validate(agent_id)
    if not issues:
        click.echo("All agents valid.")
    else:
        for issue in issues:
            click.secho(f"  {issue}", fg="red", err=True)
        raise SystemExit(1)
