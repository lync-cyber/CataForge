"""cataforge hook — hook management."""

from __future__ import annotations

import click

from cataforge.cli.main import cli
from cataforge.cli.stubs import exit_not_implemented


@cli.group("hook")
def hook_group() -> None:
    """Manage CataForge hooks."""


@hook_group.command("list")
def hook_list() -> None:
    """List all registered hooks."""
    from cataforge.hook.bridge import load_hooks_spec

    try:
        spec = load_hooks_spec()
    except (OSError, ValueError) as e:
        click.secho(f"Failed to load hooks spec: {e}", fg="red", err=True)
        raise SystemExit(1) from None

    hooks = spec.get("hooks", {})
    for event_name, hook_entries in hooks.items():
        click.echo(f"\n{event_name}:")
        for h in hook_entries:
            script = h.get("script", "?")
            desc = h.get("description", "")
            htype = h.get("type", "observe")
            click.echo(f"  {script} ({htype}) - {desc}")


@hook_group.command("test")
@click.argument("hook_name")
def hook_test(hook_name: str) -> None:
    """Test a hook with sample input."""
    exit_not_implemented(
        "Hook 测试",
        f"(hook={hook_name!r})",
        milestone="v0.2",
        workaround=(
            "直接执行脚本并喂 JSON：echo '{...}' | python .cataforge/hooks/<script>.py"
        ),
    )
