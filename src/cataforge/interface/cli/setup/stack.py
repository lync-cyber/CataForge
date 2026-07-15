"""cataforge setup stack-scoped subcommands — env-block, permissions,
gitattributes."""

from __future__ import annotations

from pathlib import Path

import click

from cataforge.interface.cli.setup import setup_command
from cataforge.utils.atomic_write import atomic_write_text


def _setup_root() -> Path:
    """Project root for stack-scoped subcommands: explicit override, else walk up."""
    from cataforge.core.paths import find_project_root_or_none
    from cataforge.interface.cli._support.helpers import resolve_project_dir

    override = resolve_project_dir()
    if override is not None:
        return override
    return find_project_root_or_none(Path.cwd()) or Path.cwd()


@setup_command.command("env-block")
def setup_env_block() -> None:
    """Print the §执行环境 Markdown block for the detected stack.

    Exit 2 when no known toolchain is detected so the caller can fall back to
    asking the user.
    """
    from cataforge.core.stack import detect_primary_stack, render_env_block

    stack = detect_primary_stack(_setup_root())
    if stack is None:
        click.echo("- 无自动检测到的标准包管理器（请根据实际技术栈手动填写）")
        raise SystemExit(2)
    click.echo(render_env_block(stack), nl=False)


@setup_command.command("permissions")
def setup_permissions() -> None:
    """Narrow the Bash allowlist in the platform settings file to the detected stack.

    Exit 2 when no stack is detected, 1 when no platform settings file exists.
    """
    import json

    from cataforge.core.stack import detect_primary_stack

    root = _setup_root()
    stack = detect_primary_stack(root)
    if stack is None:
        click.echo("no stack detected — leaving permissions unchanged", err=True)
        raise SystemExit(2)

    # Generic utility prefixes are needed regardless of stack for Bootstrap.
    allow_prefixes = [*stack.bash_allow, "git ", "ls ", "cat ", "echo "]

    settings = root / ".claude" / "settings.json"
    if settings.is_file():
        data = json.loads(settings.read_text())
        perms = data.setdefault("permissions", {})
        perms["allow"] = [f"Bash({p}*)" for p in allow_prefixes]
        atomic_write_text(settings, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        click.echo(f"updated {settings} — {len(allow_prefixes)} allow prefixes")
        return

    cursor_settings = root / ".cursor" / "hooks.json"
    if cursor_settings.is_file():
        click.echo(
            f"Cursor permissions narrowing not implemented yet — detected stack: {stack.language}",
            err=True,
        )
        return

    click.echo("no platform settings file found — nothing to update", err=True)
    raise SystemExit(1)


@setup_command.command("gitattributes")
def setup_gitattributes() -> None:
    """Ensure project-root .gitattributes line-ending defaults."""
    from cataforge.application.services.git_hygiene import ensure_gitattributes

    root = _setup_root()
    status = ensure_gitattributes(root)
    if status.wrote_file:
        click.echo("wrote .gitattributes")
        return
    if status.ok:
        click.echo("ok: .gitattributes already normalizes line endings")
        return
    click.echo(
        ".gitattributes exists but lacks `text=auto` or `eol=`; "
        "preserving user-owned file. Add line-ending rules manually.",
        err=True,
    )
    raise SystemExit(1)
