"""cataforge deploy — deploy framework to target platform(s)."""

from __future__ import annotations

from pathlib import Path

import click

from cataforge.cli.errors import ConfigError, NotInitializedError
from cataforge.cli.main import cli
from cataforge.platform.conformance import ALL_PLATFORMS

PLATFORM_CHOICES = ALL_PLATFORMS + ["all"]


def _require_scaffold(root: Path, targets: list[str], platforms_dir: Path) -> None:
    """Fail with a friendly hint when the project is not yet initialised.

    Two failure modes:
      1. No ``.cataforge/`` at all — user never ran ``cataforge setup``.
      2. ``.cataforge/`` exists but a requested platform's ``profile.yaml``
         is missing — partial/corrupt scaffold.
    """
    if not (root / ".cataforge").is_dir():
        hint_platform = targets[0] if targets and targets[0] != "all" else "claude-code"
        raise NotInitializedError(root, hint_platform=hint_platform)

    missing = [
        p for p in targets
        if p != "all" and not (platforms_dir / p / "profile.yaml").is_file()
    ]
    if missing:
        raise ConfigError(
            "Missing platform profile(s): " + ", ".join(missing) + "\n"
            f"  Expected at: {platforms_dir}/<platform>/profile.yaml\n"
            "  Re-run setup to restore the scaffold:\n"
            f"    cataforge setup --platform {missing[0]} --force-scaffold"
        )


@cli.command("deploy")
@click.option(
    "--platform",
    type=click.Choice(PLATFORM_CHOICES),
    default=None,
    help="Target platform (default: from framework.json).",
)
@click.option(
    "--dry-run", "dry_run",
    is_flag=True,
    help="Preview actions without writing files.",
)
@click.option(
    "--check",
    "check_legacy",
    is_flag=True,
    hidden=True,
    help="Deprecated alias for --dry-run. Will be removed in v0.3.",
)
@click.option("--conformance", is_flag=True, help="Run platform conformance checks only.")
def deploy_command(
    platform: str | None,
    dry_run: bool,
    check_legacy: bool,
    conformance: bool,
) -> None:
    """Deploy CataForge agents, hooks, and rules to the target platform."""
    from cataforge.cli.helpers import get_config_manager
    from cataforge.core.events import EventBus

    if check_legacy:
        click.secho(
            "[deprecated] --check is an alias for --dry-run and will be "
            "removed in v0.3. Use `cataforge deploy --dry-run` instead.",
            fg="yellow",
            err=True,
        )
        dry_run = True

    cfg = get_config_manager()
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

    _require_scaffold(cfg.paths.root, targets, cfg.paths.platforms_dir)

    from cataforge.deploy.deployer import Deployer

    deployer = Deployer(cfg, bus)

    for target in targets:
        click.echo(f"\n{'='*40}")
        click.echo(f"Deploying: {target}")
        click.echo(f"{'='*40}")

        if dry_run:
            click.echo("(dry-run — no files will be written)")
            actions = deployer.deploy(target, dry_run=True)
            for action in actions:
                click.echo(f"  {action}")
            continue

        actions = deployer.deploy(target)
        for action in actions:
            click.echo(f"  {action}")

    click.echo("\nDeploy complete.")
