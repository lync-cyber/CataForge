"""cataforge hook — hook management."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import click

from cataforge.core.errors import CataforgeError, ConfigError
from cataforge.interface.cli._support.guards import require_initialized
from cataforge.interface.cli._support.helpers import get_config_manager, resolve_root
from cataforge.interface.cli.main import cli
from cataforge.utils.interpreter import hook_command_template, interpreter_command

_SHELL_META_RE = re.compile(r"[;&|`$<>(){}\\\n]")


@cli.group("hook")
def hook_group() -> None:
    """Manage CataForge hooks.

    Hooks declared in ``.cataforge/hooks/hooks.yaml`` wire the framework
    into IDE events (PreToolUse, PostToolUse, …). Use ``list`` to see
    what's registered, ``test`` to fire a hook with a sample payload.
    """


@hook_group.command("list")
@click.option(
    "--platform",
    default=None,
    help="Show native/degraded status against this platform profile.",
)
@require_initialized
def hook_list(platform: str | None) -> None:
    """List all registered hooks.

    With ``--platform`` also annotates each hook with its status on that
    platform (native / degraded / missing tool mapping).
    """
    from cataforge.runtime.hook.bridge import load_hooks_spec

    try:
        spec = load_hooks_spec()
    except (OSError, ValueError) as e:
        raise ConfigError(f"Failed to load hooks spec: {e}") from None

    annotations: dict[str, str] = {}
    if platform:
        annotations = _platform_status_map(platform)

    from cataforge.interface.cli._support.ui import ui

    hooks = spec.get("hooks", {})
    headers = ["script", "type", "description"]
    if platform:
        headers.insert(2, "platform-status")
    for event_name, hook_entries in hooks.items():
        ui.section(event_name)
        rows: list[list[str]] = []
        for h in hook_entries:
            script = h.get("script", "?")
            desc = h.get("description", "")
            htype = h.get("type", "observe")
            row = [script, htype, desc]
            if platform:
                # Brackets are preserved so existing platform-conformance
                # tests can grep on ``[native]`` / ``[degraded]`` markers.
                status = annotations.get(script.replace(".py", ""), "?")
                row.insert(2, f"[{status}]")
            rows.append(row)
        ui.table(headers=headers, rows=rows)


def _platform_status_map(platform_id: str) -> dict[str, str]:
    """Return ``{script_name: status}`` for each canonical hook on *platform_id*."""
    try:
        from cataforge.adapter.platform.registry import get_adapter

        cfg = get_config_manager()
        adapter = get_adapter(platform_id, cfg.paths.platforms_dir)
    except Exception as e:
        click.secho(
            f"Warning: could not load adapter for {platform_id}: {e}",
            fg="yellow",
            err=True,
        )
        return {}

    return {name: policy.mode for name, policy in adapter.hook_policies.items()}


def _resolve_payload(
    root: Path, hook_name: str, fixture: Path | None, inline_input: str | None
) -> tuple[str, str]:
    """Pick the stdin payload (inline > fixture > default fixture > empty) and
    validate it as JSON so the user sees a clear error, not a hook crash."""
    if inline_input is not None:
        payload = inline_input
        source_label = "inline --input"
    elif fixture is not None:
        payload = fixture.read_text()
        source_label = str(fixture)
    else:
        default_fixture = root / ".cataforge" / "hooks" / "fixtures" / f"{hook_name}.json"
        if default_fixture.is_file():
            payload = default_fixture.read_text()
            source_label = str(default_fixture)
        else:
            payload = "{}"
            source_label = "(empty — provide --fixture or --input for realistic tests)"

    try:
        json.loads(payload)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Payload is not valid JSON: {e}") from None
    return payload, source_label


def _python_command_args(command: str) -> str | None:
    """Return the arguments after the interpreter for a python hook command,
    or None when *command* does not invoke a python interpreter we recognize
    (the current quoted ``sys.executable`` or a bare ``python``)."""
    for prefix in (f"{interpreter_command()} ", "python "):
        if command.startswith(prefix):
            return command[len(prefix) :]
    return None


def _build_proc_invocation(
    root: Path, hook_name: str, command: str
) -> tuple[dict[str, object], str]:
    """Resolve subprocess kwargs + display string for a hook command.

    Python hook commands run via the current interpreter as an argv list
    (shell=False) so a space-in-path ``sys.executable`` isn't re-parsed by
    cmd.exe, and with PYTHONPATH propagated so ``-m cataforge`` finds the
    same package. Custom commands stay shell=False + shlex.split unless the
    hook entry opts into ``unsafe_shell: true``.
    """
    unsafe_shell = _hook_has_unsafe_shell(root, hook_name)
    python_args = _python_command_args(command)
    if python_args is not None:
        argv = [sys.executable, *shlex.split(python_args)]
        proc_kwargs: dict[str, object] = {"args": argv, "shell": False}
        display = " ".join(shlex.quote(a) for a in argv)
        proc_kwargs["env"] = _child_env_with_cataforge_importable()
    elif unsafe_shell:
        proc_kwargs = {"args": command, "shell": True}
        display = command
    else:
        if _SHELL_META_RE.search(command):
            raise CataforgeError(
                f"hook command contains shell metacharacters: {command!r}\n"
                "Set unsafe_shell: true in the hook entry to allow shell interpretation."
            )
        proc_kwargs = {"args": shlex.split(command), "shell": False}
        display = command
    return proc_kwargs, display


def _report_hook_result(proc: subprocess.CompletedProcess[str], hook_name: str) -> None:
    """Echo stdout/stderr + exit verdict; mirror a non-zero child exit as a
    CataforgeError so ``hook test`` can gate shell pipelines."""
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
    if proc.returncode == 0:
        return
    err = CataforgeError(f"hook {hook_name!r} exited with code {proc.returncode} ({verdict}).")
    err.exit_code = proc.returncode
    raise err


@hook_group.command("test")
@click.argument("hook_name")
@click.option(
    "--fixture",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to stdin JSON fixture. Default: .cataforge/hooks/fixtures/<name>.json",
)
@click.option(
    "--input",
    "inline_input",
    default=None,
    help="Inline JSON payload (alternative to --fixture).",
)
@require_initialized
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
    root = resolve_root()

    command = _resolve_hook_command(root, hook_name)
    if command is None:
        raise ConfigError(
            f"No hook named {hook_name!r} declared in hooks.yaml.\n"
            "Run `cataforge hook list` to see registered hooks."
        )

    payload, source_label = _resolve_payload(root, hook_name, fixture, inline_input)
    proc_kwargs, display = _build_proc_invocation(root, hook_name, command)

    click.echo(f"Hook    : {hook_name}")
    click.echo(f"Command : {display}")
    click.echo(f"Payload : {source_label}")
    click.echo("-" * 40)

    # The wrapper only takes argv positionally; this site needs to pass args/shell
    # via **proc_kwargs (shell=True for unsafe_shell hooks).
    proc = subprocess.run(  # type: ignore[call-overload]  # allow-raw-subprocess: shell=True for unsafe_shell hooks
        input=payload,
        capture_output=True,
        text=True,
        cwd=root,
        **proc_kwargs,
    )

    _report_hook_result(proc, hook_name)


def _child_env_with_cataforge_importable() -> dict[str, str]:
    """Copy ``os.environ`` with ``PYTHONPATH`` prepended so the child can
    ``import cataforge`` from the same location as this interpreter.

    ``site-packages`` setups aren't affected: the child's default search
    already covers them and ``PYTHONPATH`` only gets checked before
    ``site-packages`` — no duplication, no surprise shadowing of a
    user-installed ``cataforge``.
    """
    env = os.environ.copy()
    try:
        import cataforge  # noqa: PLC0415 — lazy so import errors are caught

        pkg_file = Path(cataforge.__file__ or "").resolve()
    except Exception:
        return env
    if not pkg_file.is_file():
        return env
    pkg_parent = str(pkg_file.parent.parent)
    existing = env.get("PYTHONPATH", "")
    parts = existing.split(os.pathsep) if existing else []
    if pkg_parent in parts:
        return env
    env["PYTHONPATH"] = os.pathsep.join([pkg_parent, *parts]) if parts else pkg_parent
    return env


def _resolve_hook_command(root: Path, hook_name: str) -> str | None:
    """Return the shell command that invokes *hook_name*, or None."""
    if not re.fullmatch(r"[a-zA-Z0-9_]+", hook_name):
        raise CataforgeError(f"invalid hook name: {hook_name!r} (must match [a-zA-Z0-9_]+)")

    from cataforge.runtime.hook.bridge import _resolve_command, load_hooks_spec

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
                return _resolve_command(hook_command_template(), normalised)

    # If the user passes an undeclared built-in script name, we still
    # allow running it (handy for quick iteration).
    builtin = (
        root / ".." / ".." / ".." / "src" / "cataforge" / "hook" / "scripts" / f"{hook_name}.py"
    ).resolve()
    if builtin.is_file():
        return hook_command_template().format(module=hook_name)

    return None


def _hook_has_unsafe_shell(root: Path, hook_name: str) -> bool:
    """Return True if the hook entry in hooks.yaml has ``unsafe_shell: true``."""
    from cataforge.runtime.hook.bridge import load_hooks_spec

    try:
        spec = load_hooks_spec()
    except (OSError, ValueError):
        return False

    for event_hooks in (spec.get("hooks") or {}).values():
        for entry in event_hooks or []:
            declared = str(entry.get("script", ""))
            normalised = declared.replace(".py", "")
            if normalised == hook_name or normalised == f"custom:{hook_name}":
                return bool(entry.get("unsafe_shell", False))
    return False


def _interpret_exit(code: int) -> str:
    """Human-readable mapping from exit code to hook semantics."""
    if code == 0:
        return "OK (allow / observation recorded)"
    if code == 2:
        return "BLOCKED (hook refused tool execution)"
    return f"ERROR (non-standard exit {code})"
