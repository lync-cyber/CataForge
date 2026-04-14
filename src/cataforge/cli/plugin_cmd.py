"""cataforge plugin — plugin management."""

from __future__ import annotations

import click

from cataforge.cli.main import cli
from cataforge.cli.stubs import exit_not_implemented


@cli.group("plugin")
def plugin_group() -> None:
    """Manage CataForge plugins."""


@plugin_group.command("list")
def plugin_list() -> None:
    """List all discovered plugins."""
    from cataforge.plugin.loader import PluginLoader

    loader = PluginLoader()
    plugins = loader.discover()
    if not plugins:
        click.echo("No plugins found.")
        return
    for p in plugins:
        click.echo(f"  {p.id} v{p.version}: {p.name}")


@plugin_group.command("install")
@click.argument("name")
def plugin_install(name: str) -> None:
    """Install a plugin."""
    exit_not_implemented(
        "插件安装",
        f"请用 pip 安装带 cataforge.plugins 入口的包，或使用 .cataforge/plugins/。 (name={name!r})",
    )


@plugin_group.command("remove")
@click.argument("name")
def plugin_remove(name: str) -> None:
    """Remove a plugin."""
    exit_not_implemented("插件卸载", f"(name={name!r})")
