"""cataforge skill — skill management."""

from __future__ import annotations

import click

from cataforge.cli.main import cli


@cli.group("skill")
def skill_group() -> None:
    """Manage CataForge skills."""


@skill_group.command("list")
def skill_list() -> None:
    """List all available skills."""
    from cataforge.skill.loader import SkillLoader

    loader = SkillLoader()
    skills = loader.discover()
    if not skills:
        click.echo("No skills found.")
        return
    for s in skills:
        click.echo(f"  {s.id} ({s.skill_type.value}): {s.name}")


@skill_group.command("run")
@click.argument("skill_id")
@click.argument("args", nargs=-1)
def skill_run(skill_id: str, args: tuple[str, ...]) -> None:
    """Run an executable skill."""
    from cataforge.skill.runner import SkillRunner

    try:
        runner = SkillRunner()
        result = runner.run(skill_id, list(args))
        click.echo(result.stdout)
        if result.returncode == 0:
            if result.stderr and result.stderr.strip():
                click.secho(result.stderr, fg="yellow", err=True)
        else:
            click.secho(result.stderr, fg="red", err=True)
            raise SystemExit(result.returncode)
    except (ValueError, FileNotFoundError) as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        raise SystemExit(1) from None
