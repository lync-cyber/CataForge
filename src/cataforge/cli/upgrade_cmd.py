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
    """Manage framework upgrades.

    The Python package is upgraded via pip/uv; ``apply`` then refreshes
    the in-project scaffold. ``verify`` is an alias for ``doctor``.
    """


@upgrade_group.command("check")
def upgrade_check() -> None:
    """Compare the in-project scaffold version against the installed package."""
    from cataforge.cli.helpers import get_config_manager

    cfg = get_config_manager()
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
def upgrade_apply(dry_run: bool) -> None:
    """Refresh the in-project scaffold against the installed package.

    Equivalent to ``cataforge setup --force-scaffold`` — the package
    itself must be upgraded separately via pip/uv.
    """
    from cataforge.cli.helpers import get_config_manager
    from cataforge.core.scaffold import copy_scaffold_to, iter_scaffold_files

    if dry_run:
        paths = sorted(rel for rel, _ in iter_scaffold_files())
        click.echo(f"Would refresh {len(paths)} scaffold file(s).")
        click.echo(
            "User-owned state preserved: framework.json(runtime.platform, "
            "upgrade.state), PROJECT-STATE.md"
        )
        return

    # Direct scaffold refresh — avoids the fragile ctx.invoke(setup_command, ...)
    # pattern which was silently sensitive to changes in setup's parameter list.
    cfg = get_config_manager()
    dest = cfg.paths.cataforge_dir
    click.echo(f"Refreshing .cataforge/ at {dest}")
    written, skipped = copy_scaffold_to(dest, force=True)
    click.echo(
        f"  wrote {len(written)} file(s)"
        + (f", kept {len(skipped)} existing" if skipped else "")
    )
    cfg.reload()
    click.echo(f"CataForge v{cfg.version} — scaffold up to date.")


@upgrade_group.command("verify")
@click.pass_context
def upgrade_verify(ctx: click.Context) -> None:
    """Run migration checks (alias for ``cataforge doctor``)."""
    # Importing the command here keeps module import time low and makes
    # the aliasing explicit. ctx.invoke preserves any parent flags the
    # user passed (e.g. --verbose/--quiet/--project-dir).
    from cataforge.cli.doctor_cmd import doctor_command

    ctx.invoke(doctor_command)
