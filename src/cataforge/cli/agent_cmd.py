"""cataforge agent — agent management."""

from __future__ import annotations

import click

from cataforge.cli.errors import CataforgeError
from cataforge.cli.guards import require_initialized
from cataforge.cli.helpers import emit_hint, resolve_root
from cataforge.cli.main import cli


@cli.group("agent")
def agent_group() -> None:
    """Manage CataForge agents.

    Agents are defined in ``.cataforge/agents/<id>/AGENT.md``. Use
    ``cataforge agent list`` to see what's registered and
    ``cataforge agent validate [id]`` to check a definition.
    """


@agent_group.command("list")
@require_initialized
def agent_list() -> None:
    """List all registered agents (from ``.cataforge/agents/``)."""
    from cataforge.agent.manager import AgentManager

    mgr = AgentManager(project_root=resolve_root())
    agents = mgr.list_agents()
    if not agents:
        click.echo("No agents found.")
        emit_hint(
            "  Hint: scaffold with `cataforge setup --force-scaffold`, "
            "or add a new agent directory under .cataforge/agents/<id>/."
        )
        return
    for a in agents:
        click.echo(f"  {a}")


@agent_group.command("validate")
@click.argument("agent_id", required=False)
@require_initialized
def agent_validate(agent_id: str | None) -> None:
    """Validate one agent (by id) or all agents if no id is given.

    Checks AGENT.md frontmatter, declared tools, and model field.
    Fails with exit 1 if any issue is found, so it can gate CI.
    """
    from cataforge.agent.manager import AgentManager

    mgr = AgentManager(project_root=resolve_root())
    issues = mgr.validate(agent_id)
    if not issues:
        click.echo("All agents valid.")
        return

    for issue in issues:
        click.secho(f"  {issue}", fg="red", err=True)
    raise CataforgeError(f"{len(issues)} agent definition issue(s) found.")
