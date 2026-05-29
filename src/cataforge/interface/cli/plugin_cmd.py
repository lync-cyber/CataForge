"""cataforge plugin — plugin management."""

from __future__ import annotations

import click

from cataforge.interface.cli.guards import require_initialized
from cataforge.interface.cli.helpers import emit_hint, resolve_root
from cataforge.interface.cli.main import cli
from cataforge.interface.cli.stubs import exit_not_implemented


@cli.group("plugin")
def plugin_group() -> None:
    """Manage CataForge plugins.

    Plugins extend the framework with custom skills, agents, or platform
    adapters. They are discovered via the ``cataforge.plugins`` entry
    point group or from ``.cataforge/plugins/<id>/``.

    Available now: ``list``. The ``install`` / ``remove`` subcommands are
    not implemented yet — use ``pip install <pkg>`` or drop a folder
    under ``.cataforge/plugins/<id>/`` directly in the meantime. Track
    progress at https://github.com/lync-cyber/CataForge/issues.
    """


@plugin_group.command("list")
@require_initialized
def plugin_list() -> None:
    """List all discovered plugins (entry-point + local)."""
    from cataforge.interface.cli.ui import ui
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
@click.argument("name")
def plugin_install(name: str) -> None:
    """[未实现 · 规划中] Install a plugin.

    This command always exits 70 (NotImplementedFeature). Use ``pip install
    <pkg>`` for entry-point plugins, or drop the plugin folder into
    ``.cataforge/plugins/<id>/`` for local plugins.
    """
    exit_not_implemented(
        "插件安装",
        f"(name={name!r})",
        workaround=(
            f"pip install {name}  # 包需声明 cataforge.plugins entry_point；"
            "或将插件目录放入 .cataforge/plugins/<id>/ 并附带 cataforge-plugin.yaml"
        ),
    )


@plugin_group.command("remove")
@click.argument("name")
def plugin_remove(name: str) -> None:
    """[未实现 · 规划中] Remove a plugin.

    This command always exits 70 (NotImplementedFeature). Use ``pip
    uninstall <pkg>`` for entry-point plugins, or delete the plugin folder
    at ``.cataforge/plugins/<id>/`` for local plugins.
    """
    exit_not_implemented(
        "插件卸载",
        f"(name={name!r})",
        workaround=(
            f"pip uninstall {name}  # 或删除 .cataforge/plugins/{name}/ 目录"
        ),
    )
