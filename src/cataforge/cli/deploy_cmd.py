"""cataforge deploy — deploy framework to target platform(s)."""

from __future__ import annotations

import click

from cataforge.cli.main import cli
from cataforge.platform.conformance import ALL_PLATFORMS

PLATFORM_CHOICES = ALL_PLATFORMS + ["all"]


@cli.command("deploy")
@click.option(
    "--platform",
    type=click.Choice(PLATFORM_CHOICES),
    default=None,
    help="Target platform (default: from framework.json).",
)
@click.option(
    "--check",
    is_flag=True,
    help="Dry-run: list actions that would be performed without writing files.",
)
@click.option("--conformance", is_flag=True, help="Run platform conformance checks only.")
def deploy_command(platform: str | None, check: bool, conformance: bool) -> None:
    """Deploy CataForge agents, hooks, and rules to the target platform."""
    from cataforge.core.config import ConfigManager
    from cataforge.core.events import EventBus

    cfg = ConfigManager()
    bus = EventBus()

    if conformance:
        from cataforge.platform.conformance import check_all_conformance

        issues = check_all_conformance()
        for issue in issues:
            click.echo(issue)
        if not issues:
            click.echo("All platforms conformant.")
        return

    targets: list[str] = []
    if platform == "all":
        targets = list(ALL_PLATFORMS)
    elif platform:
        targets = [platform]
    else:
        targets = [cfg.runtime_platform]

    from cataforge.deploy.deployer import Deployer

    deployer = Deployer(cfg, bus)

    for target in targets:
        click.echo(f"\n{'='*40}")
        click.echo(f"Deploying: {target}")
        click.echo(f"{'='*40}")

        if check:
            click.echo("(dry-run — no files will be written)")
            actions = deployer.deploy(target, dry_run=True)
            for action in actions:
                click.echo(f"  {action}")
            continue

        actions = deployer.deploy(target)
        for action in actions:
            click.echo(f"  {action}")

    click.echo("\nDeploy complete.")
