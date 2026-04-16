"""cataforge hook — hook management."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import click

from cataforge.cli.main import cli


@cli.group("hook")
def hook_group() -> None:
    """Manage CataForge hooks."""


@hook_group.command("list")
@click.option(
    "--platform",
    default=None,
    help="Show native/degraded status against this platform profile.",
)
def hook_list(platform: str | None) -> None:
    """List all registered hooks.

    With ``--platform`` also annotates each hook with its status on that
    platform (native / degraded / missing tool mapping).
    """
    from cataforge.hook.bridge import load_hooks_spec

    try:
        spec = load_hooks_spec()
    except (OSError, ValueError) as e:
        click.secho(f"Failed to load hooks spec: {e}", fg="red", err=True)
        raise SystemExit(1) from None

    annotations: dict[str, str] = {}
    if platform:
        annotations = _platform_status_map(platform)

    hooks = spec.get("hooks", {})
    for event_name, hook_entries in hooks.items():
        click.echo(f"\n{event_name}:")
        for h in hook_entries:
            script = h.get("script", "?")
            desc = h.get("description", "")
            htype = h.get("type", "observe")
            status = f" [{annotations.get(script.replace('.py', ''), '?')}]" if platform else ""
            click.echo(f"  {script} ({htype}){status} - {desc}")


def _platform_status_map(platform_id: str) -> dict[str, str]:
    """Return ``{script_name: status}`` for each canonical hook on *platform_id*."""
    try:
        from cataforge.core.config import ConfigManager
        from cataforge.platform.registry import get_adapter

        cfg = ConfigManager()
        adapter = get_adapter(platform_id, cfg.paths.platforms_dir)
    except Exception as e:
        click.secho(f"Warning: could not load adapter for {platform_id}: {e}", fg="yellow", err=True)
        return {}

    return {name: status for name, status in adapter.hook_degradation.items()}


@hook_group.command("test")
@click.argument("hook_name")
@click.option(
    "--fixture",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to stdin JSON fixture. Default: .cataforge/hooks/fixtures/<name>.json",
)
@click.option(
    "--input", "inline_input",
    default=None,
    help="Inline JSON payload (alternative to --fixture).",
)
def hook_test(hook_name: str, fixture: Path | None, inline_input: str | None) -> None:
    """Run a hook script with a sample payload.

    Looks up the script from ``hooks.yaml`` (including ``custom:`` entries)
    and executes it with either:

    * the ``--fixture`` file,
    * the ``--input`` inline JSON, or
    * ``.cataforge/hooks/fixtures/<name>.json`` if present, else ``{}``.

    Prints exit code + stderr so users can verify block/observe behaviour
    locally without going through a full deploy → IDE cycle.
    """
    from cataforge.core.paths import find_project_root

    root = find_project_root()

    # Resolve the invocation command for hook_name.
    command = _resolve_hook_command(root, hook_name)
    if command is None:
        click.secho(
            f"No hook named {hook_name!r} declared in hooks.yaml.\n"
            "Run `cataforge hook list` to see registered hooks.",
            fg="red",
            err=True,
        )
        raise SystemExit(1)

    # Pick the stdin payload.
    payload: str
    source_label: str
    if inline_input is not None:
        payload = inline_input
        source_label = "inline --input"
    elif fixture is not None:
        payload = fixture.read_text(encoding="utf-8")
        source_label = str(fixture)
    else:
        default_fixture = (
            root / ".cataforge" / "hooks" / "fixtures" / f"{hook_name}.json"
        )
        if default_fixture.is_file():
            payload = default_fixture.read_text(encoding="utf-8")
            source_label = str(default_fixture)
        else:
            payload = "{}"
            source_label = "(empty — provide --fixture or --input for realistic tests)"

    # Validate JSON early so the user sees a clear error instead of a hook crash.
    try:
        json.loads(payload)
    except json.JSONDecodeError as e:
        click.secho(f"Payload is not valid JSON: {e}", fg="red", err=True)
        raise SystemExit(1) from None

    # Use the current interpreter — it already has cataforge importable,
    # which the system ``python`` on $PATH may not when cataforge is
    # installed via uv tool.  Built-in hook commands start with "python"
    # exactly; rewrite that token.
    if command.startswith("python "):
        exec_command = f"{sys.executable} {command[len('python '):]}"
    else:
        exec_command = command

    click.echo(f"Hook    : {hook_name}")
    click.echo(f"Command : {exec_command}")
    click.echo(f"Payload : {source_label}")
    click.echo("-" * 40)

    proc = subprocess.run(
        exec_command,
        input=payload,
        capture_output=True,
        text=True,
        shell=True,
        cwd=root,
    )

    if proc.stdout:
        click.echo("stdout:")
        click.echo(proc.stdout.rstrip())
    if proc.stderr:
        click.echo("stderr:")
        click.echo(proc.stderr.rstrip())

    click.echo("-" * 40)
    click.echo(f"Exit code: {proc.returncode}")
    verdict = _interpret_exit(proc.returncode)
    click.echo(f"Verdict  : {verdict}")

    # Mirror the hook's exit code so `hook test` can gate shell pipelines.
    sys.exit(proc.returncode)


def _resolve_hook_command(root: Path, hook_name: str) -> str | None:
    """Return the shell command that invokes *hook_name*, or None."""
    from cataforge.hook.bridge import _resolve_command, load_hooks_spec

    try:
        spec = load_hooks_spec()
    except (OSError, ValueError):
        return None

    # Accept both bare and ``custom:`` names.
    for event_hooks in (spec.get("hooks") or {}).values():
        for entry in event_hooks or []:
            declared = str(entry.get("script", ""))
            normalised = declared.replace(".py", "")
            if normalised == hook_name or normalised == f"custom:{hook_name}":
                template = "python -m cataforge.hook.scripts.{module}"
                return _resolve_command(template, normalised)

    # If the user passes an undeclared built-in script name, we still
    # allow running it (handy for quick iteration).
    builtin = (
        root
        / ".." / ".."
        / ".."
        / "src"
        / "cataforge"
        / "hook"
        / "scripts"
        / f"{hook_name}.py"
    ).resolve()
    if builtin.is_file():
        return f"python -m cataforge.hook.scripts.{hook_name}"

    return None


def _interpret_exit(code: int) -> str:
    """Human-readable mapping from exit code to hook semantics."""
    if code == 0:
        return "OK (allow / observation recorded)"
    if code == 2:
        return "BLOCKED (hook refused tool execution)"
    return f"ERROR (non-standard exit {code})"
