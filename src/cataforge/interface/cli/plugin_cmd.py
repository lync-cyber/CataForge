"""cataforge plugin — plugin management."""

from __future__ import annotations

from pathlib import Path

import click

from cataforge.interface.cli._support.guards import require_initialized
from cataforge.interface.cli._support.helpers import emit_hint, resolve_root
from cataforge.interface.cli.main import cli


@cli.group("plugin")
def plugin_group() -> None:
    """Manage CataForge plugins.

    Plugins extend the framework with custom skills, agents, hooks, or MCP
    servers. They are discovered via the ``cataforge.plugins`` entry point
    group (pip-installed) or from ``.cataforge/plugins/<id>/`` (local).

    ``install`` copies a local plugin dir into ``.cataforge/plugins/`` or
    ``pip install``s a packaged one; ``remove`` reverses either.
    """


@plugin_group.command("list")
@require_initialized
def plugin_list() -> None:
    """List all discovered plugins (entry-point + local)."""
    from cataforge.interface.cli._support.ui import ui
    from cataforge.runtime.plugin.loader import PluginLoader

    loader = PluginLoader(project_root=resolve_root())
    plugins = loader.discover()
    if not plugins:
        click.echo("No plugins found.")
        emit_hint(
            "  Hint: install with `pip install <pkg>` (must declare the "
            "`cataforge.plugins` entry point) or drop a plugin folder into "
            ".cataforge/plugins/<id>/."
        )
        return
    ui.table(
        headers=["id", "version", "name"],
        rows=[[p.id, p.version, p.name] for p in plugins],
    )


@plugin_group.command("install")
@click.argument("source")
@click.option("--force", is_flag=True, help="Overwrite an existing local plugin dir.")
@require_initialized
def plugin_install(source: str, force: bool) -> None:
    """Install a plugin from a local directory or a pip package.

    SOURCE that is an existing directory containing ``cataforge-plugin.yaml``
    is copied into ``.cataforge/plugins/<id>/``. Otherwise SOURCE is treated
    as a pip requirement and installed (the package must declare a
    ``cataforge.plugins`` entry point to be discovered).
    """
    import shutil

    from cataforge.core.paths import ProjectPaths
    from cataforge.core.schema.plugin_manifest import PluginManifest

    src = Path(source)
    manifest_file = src / "cataforge-plugin.yaml"
    if src.is_dir() and manifest_file.is_file():
        manifest = PluginManifest.from_yaml_file(manifest_file)
        dest = ProjectPaths(resolve_root()).plugins_dir / manifest.id
        if dest.exists():
            if not force:
                raise click.ClickException(
                    f"plugin {manifest.id!r} already installed at {dest}; pass --force to overwrite"
                )
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
        click.echo(f"installed local plugin {manifest.id!r} → {dest}")
        click.echo("run `cataforge deploy` to materialise its assets.")
        return

    if src.is_dir():
        raise click.ClickException(
            f"{source}: directory has no cataforge-plugin.yaml — not a local plugin"
        )

    _pip(["install", source])
    click.echo(f"pip-installed {source!r}; entry-point plugins are auto-discovered.")
    click.echo("run `cataforge deploy` to materialise its assets.")


@plugin_group.command("remove")
@click.argument("name")
@require_initialized
def plugin_remove(name: str) -> None:
    """Remove a plugin: a local ``.cataforge/plugins/<name>/`` dir, else a pip package."""
    import shutil

    from cataforge.core.paths import ProjectPaths

    local = ProjectPaths(resolve_root()).plugins_dir / name
    if local.is_dir():
        shutil.rmtree(local)
        click.echo(f"removed local plugin {name!r} ({local})")
        click.echo("run `cataforge deploy` to drop its materialised assets.")
        return

    _pip(["uninstall", "-y", name])
    click.echo(f"pip-uninstalled {name!r}.")


def _pip(args: list[str]) -> None:
    import sys

    from cataforge.utils.run_subprocess import run as run_proc

    result = run_proc([sys.executable, "-m", "pip", *args], timeout=600)
    if result.returncode != 0:
        raise click.ClickException(
            f"pip {args[0]} failed (exit {result.returncode}):\n"
            f"{(result.stdout + result.stderr).strip()}"
        )
