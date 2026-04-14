"""cataforge setup — project initialization."""

from __future__ import annotations

import click

from cataforge.cli.main import cli
from cataforge.platform.conformance import ALL_PLATFORMS


@cli.command("setup")
@click.option(
    "--platform",
    type=click.Choice(ALL_PLATFORMS),
    default=None,
    help="Target AI IDE platform.",
)
@click.option("--with-penpot", is_flag=True, help="Include Penpot design integration.")
@click.option("--check-only", is_flag=True, help="Only check prerequisites, do not install.")
def setup_command(platform: str | None, with_penpot: bool, check_only: bool) -> None:
    """Initialize CataForge in the current project."""
    from cataforge.core.config import ConfigManager
    from cataforge.core.events import FRAMEWORK_SETUP, EventBus

    cfg = ConfigManager()
    bus = EventBus()

    click.echo(f"CataForge v{cfg.version} — setup")
    click.echo(f"Project root: {cfg.paths.root}")

    if not cfg.paths.cataforge_dir.is_dir():
        click.secho(
            "ERROR: .cataforge/ directory not found. Is this a CataForge project?",
            fg="red",
            err=True,
        )
        raise SystemExit(1)

    if check_only:
        _run_checks(cfg)
        return

    if platform:
        cfg.set_runtime_platform(platform)
        click.echo(f"Platform set to: {platform}")

    target = platform or cfg.runtime_platform
    click.echo(f"Deploying for platform: {target}")

    from cataforge.deploy.deployer import Deployer

    deployer = Deployer(cfg, bus)
    actions = deployer.deploy(target)
    for action in actions:
        click.echo(f"  {action}")

    bus.emit(FRAMEWORK_SETUP, {"platform": target, "with_penpot": with_penpot})
    click.echo("Setup complete.")


def _run_checks(cfg) -> None:
    """Quick prerequisite checks."""
    import shutil
    import sys

    click.echo(f"Python: {sys.version}")
    click.echo(f"framework.json: {'OK' if cfg.paths.framework_json.is_file() else 'MISSING'}")
    click.echo(f"hooks.yaml: {'OK' if cfg.paths.hooks_spec.is_file() else 'MISSING'}")

    for tool in ("ruff", "npx", "docker"):
        found = shutil.which(tool) is not None
        click.echo(f"{tool}: {'found' if found else 'not found'}")
