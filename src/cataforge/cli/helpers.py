"""Small helpers shared by CLI command modules.

Kept separate from ``main.py`` so command modules don't pull the Click
group (and transitively every registered command) when they just need a
``ConfigManager`` that honours the global ``--project-dir`` flag.
"""

from __future__ import annotations

from pathlib import Path

import click


def resolve_project_dir() -> Path | None:
    """Return the ``--project-dir`` override if the current Click context
    has one, else ``None``. Safe to call outside a Click context (returns
    ``None``)."""
    try:
        ctx = click.get_current_context(silent=True)
    except Exception:
        return None
    if ctx is None or not isinstance(getattr(ctx, "obj", None), dict):
        return None
    from cataforge.cli.main import CTX_PROJECT_DIR

    override = ctx.obj.get(CTX_PROJECT_DIR)
    return Path(override) if override else None


def get_config_manager():
    """Return a :class:`ConfigManager` honouring ``--project-dir`` if set.

    All CLI commands should instantiate their ConfigManager through this
    helper so the global flag has the intended effect.
    """
    from cataforge.core.config import ConfigManager

    override = resolve_project_dir()
    return ConfigManager(project_root=override)


def resolve_root() -> Path:
    """Return the project root honouring ``--project-dir``.

    This is the single entry point used by every CLI subcommand that
    instantiates a manager/loader (``AgentManager``, ``SkillLoader``,
    ``MCPRegistry``, ``PluginLoader``, …). Each of those classes
    accepts ``project_root`` and falls back to ``find_project_root()``
    when passed ``None``; this helper routes the global flag through.
    """
    from cataforge.core.paths import find_project_root

    return resolve_project_dir() or find_project_root()


def emit_hint(message: str) -> None:
    """Print a dim hint line on stderr (used after empty-result banners)."""
    click.secho(message, fg="bright_black", err=True)


__all__ = ["emit_hint", "get_config_manager", "resolve_project_dir", "resolve_root"]
