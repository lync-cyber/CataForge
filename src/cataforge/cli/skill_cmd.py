"""cataforge skill — skill management."""

from __future__ import annotations

import click

from cataforge.cli.errors import CataforgeError, ConfigError
from cataforge.cli.guards import require_initialized
from cataforge.cli.helpers import emit_hint, resolve_root
from cataforge.cli.main import cli


@cli.group("skill")
def skill_group() -> None:
    """Manage CataForge skills.

    Skills live under ``.cataforge/skills/<id>/SKILL.md``. Some skills
    are plain playbooks; others are executable via ``cataforge skill run``.
    """


@skill_group.command("list")
@require_initialized
def skill_list() -> None:
    """List all skills discovered under ``.cataforge/skills/``."""
    from cataforge.skill.loader import SkillLoader

    loader = SkillLoader(project_root=resolve_root())
    skills = loader.discover()
    if not skills:
        click.echo("No skills found.")
        emit_hint(
            "  Hint: scaffold with `cataforge setup --force-scaffold`, "
            "or add a new skill directory under .cataforge/skills/<id>/."
        )
        return
    for s in skills:
        click.echo(f"  {s.id} ({s.skill_type.value}): {s.name}")


@skill_group.command("run")
@click.argument("skill_id")
@click.argument("args", nargs=-1)
@require_initialized
def skill_run(skill_id: str, args: tuple[str, ...]) -> None:
    """Run an executable skill, forwarding ARGS to the skill's entry point.

    Exits with the skill's own return code so shell pipelines can gate on
    it. Non-executable skills raise a ConfigError.
    """
    from cataforge.skill.runner import SkillRunner

    try:
        runner = SkillRunner(project_root=resolve_root())
        result = runner.run(skill_id, list(args))
    except (ValueError, FileNotFoundError) as e:
        raise ConfigError(str(e)) from None

    if result.stdout:
        click.echo(result.stdout)
    if result.returncode == 0:
        if result.stderr and result.stderr.strip():
            # Skill succeeded but emitted warnings — surface them without
            # making the exit code non-zero.
            click.secho(result.stderr, fg="yellow", err=True)
        return

    if result.stderr:
        click.secho(result.stderr, fg="red", err=True)
    # Preserve the child's exit code rather than coercing to 1 — shell
    # pipelines that dispatch on specific codes (e.g. 2 for block) still work.
    err = CataforgeError(f"skill {skill_id!r} exited with code {result.returncode}.")
    err.exit_code = result.returncode
    raise err
