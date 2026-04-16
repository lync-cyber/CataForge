"""cataforge setup — project initialization."""

from __future__ import annotations

from pathlib import Path

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
@click.option(
    "--force-scaffold",
    is_flag=True,
    help="Re-copy the bundled .cataforge/ scaffold, overwriting existing files.",
)
@click.option(
    "--deploy",
    "deploy_after",
    is_flag=True,
    help="After scaffolding, also run `cataforge deploy` for the selected platform.",
)
@click.option(
    "--no-deploy",
    is_flag=True,
    hidden=True,
    help="Deprecated: --no-deploy is now the default. Retained for compatibility.",
)
def setup_command(
    platform: str | None,
    with_penpot: bool,
    check_only: bool,
    force_scaffold: bool,
    deploy_after: bool,
    no_deploy: bool,
) -> None:
    """Initialize CataForge in the current project.

    Semantics (as of v0.1.2):

    * ``setup`` materialises ``.cataforge/`` and records the target platform,
      but does **not** write IDE-visible artifacts (``CLAUDE.md``,
      ``.claude/agents/``, ``.mcp.json``, …).  This matches the five-step
      pipeline in ``docs/manual-verification-guide.md``.
    * Run ``cataforge deploy`` as a separate step, or pass ``--deploy`` to
      chain the two for backwards compatibility.
    * ``--no-deploy`` is retained as a no-op flag so existing scripts (and
      ``cataforge upgrade apply``, which used it explicitly) still work.
    """
    from cataforge.core.config import ConfigManager
    from cataforge.core.events import FRAMEWORK_SETUP, EventBus

    # find_project_root walks up for an existing .cataforge/; when nothing is
    # found it falls back to cwd — exactly what we want for a fresh install.
    cfg = ConfigManager()
    bus = EventBus()

    click.echo(f"Project root: {cfg.paths.root}")

    scaffold_dir = cfg.paths.cataforge_dir
    if not scaffold_dir.is_dir() or force_scaffold:
        _scaffold(scaffold_dir, force=force_scaffold)
        # Re-read framework.json now that it exists on disk — without this
        # reload, the version banner below would show the pre-scaffold default
        # ("0.0.0") instead of the real bundled version.
        cfg.reload()

    click.echo(f"CataForge v{cfg.version} — setup")

    if check_only:
        _run_checks(cfg)
        return

    if platform:
        cfg.set_runtime_platform(platform)
        click.echo(f"Platform set to: {platform}")

    # --no-deploy and "neither --deploy nor --no-deploy" both mean: skip deploy.
    if not deploy_after or no_deploy:
        bus.emit(
            FRAMEWORK_SETUP,
            {"platform": platform, "with_penpot": with_penpot, "scaffold_only": True},
        )
        click.echo(
            "Setup complete. Run `cataforge deploy` to write IDE artifacts."
        )
        return

    target = platform or cfg.runtime_platform
    click.echo(f"Deploying for platform: {target}")

    from cataforge.deploy.deployer import Deployer

    deployer = Deployer(cfg, bus)
    actions = deployer.deploy(target)
    for action in actions:
        click.echo(f"  {action}")

    bus.emit(FRAMEWORK_SETUP, {"platform": target, "with_penpot": with_penpot})
    click.echo("Setup complete.")


def _scaffold(dest: Path, *, force: bool) -> None:
    """Copy the bundled .cataforge/ skeleton into *dest*."""
    from cataforge.core.scaffold import copy_scaffold_to

    action = "Refreshing" if dest.is_dir() else "Scaffolding"
    click.echo(f"{action} .cataforge/ at {dest}")
    written, skipped = copy_scaffold_to(dest, force=force)
    click.echo(f"  wrote {len(written)} file(s)" + (f", kept {len(skipped)} existing" if skipped else ""))


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
