"""cataforge upgrade — framework upgrade management.

CataForge's upgrade model is **package-manager driven**: the Python package
is upgraded via ``pip install --upgrade cataforge`` or ``uv tool upgrade
cataforge``, after which ``cataforge setup --force-scaffold`` refreshes the
in-project ``.cataforge/`` scaffold while preserving user-owned state
(``runtime.platform``, ``upgrade.state``, ``PROJECT-STATE.md``).

There is no in-repo self-upgrade mechanism — that would duplicate and diverge
from the package manager's version resolution. ``cataforge upgrade apply``
simply refreshes the scaffold against the currently-installed package.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version

import click

from cataforge.cli.main import cli


@cli.group("upgrade")
def upgrade_group() -> None:
    """Manage framework upgrades."""


@upgrade_group.command("check")
def upgrade_check() -> None:
    """Compare the in-project scaffold version against the installed package."""
    from cataforge.core.config import ConfigManager

    cfg = ConfigManager()
    scaffold_version = cfg.version
    try:
        installed = _pkg_version("cataforge")
    except PackageNotFoundError:
        installed = "unknown"

    click.echo(f"Installed package : {installed}")
    click.echo(f"Scaffold version  : {scaffold_version}")

    if installed == "unknown":
        click.echo(
            "\nCould not detect installed package version. "
            "Run `pip show cataforge` or `uv tool list` to verify."
        )
        return

    if scaffold_version == installed:
        click.echo("\nScaffold is up to date with the installed package.")
        return

    click.echo(
        "\nScaffold differs from installed package. Refresh with:\n"
        "  cataforge setup --force-scaffold\n"
        "\nTo upgrade the package itself first:\n"
        "  pip install --upgrade cataforge   # or: uv tool upgrade cataforge"
    )


@upgrade_group.command("apply")
@click.option("--dry-run", is_flag=True, help="Show what would change without applying.")
@click.pass_context
def upgrade_apply(ctx: click.Context, dry_run: bool) -> None:
    """Refresh the in-project scaffold against the installed package.

    Equivalent to ``cataforge setup --force-scaffold --no-deploy`` — the
    package itself must be upgraded separately via pip/uv.
    """
    if dry_run:
        from cataforge.core.scaffold import iter_scaffold_files

        paths = sorted(rel for rel, _ in iter_scaffold_files())
        click.echo(f"Would refresh {len(paths)} scaffold file(s).")
        click.echo(
            "User-owned state preserved: framework.json(runtime.platform, "
            "upgrade.state), PROJECT-STATE.md"
        )
        return

    from cataforge.cli.setup_cmd import setup_command

    ctx.invoke(
        setup_command,
        platform=None,
        with_penpot=False,
        check_only=False,
        force_scaffold=True,
        deploy_after=False,
        no_deploy=True,
    )


@upgrade_group.command("verify")
@click.pass_context
def upgrade_verify(ctx: click.Context) -> None:
    """Run migration checks (alias for ``cataforge doctor``)."""
    from cataforge.cli.doctor_cmd import doctor_command

    ctx.invoke(doctor_command)
