"""Small helpers shared by CLI command modules.

Kept separate from ``main.py`` so command modules don't pull the Click
group (and transitively every registered command) when they just need a
``ConfigManager`` that honours the global ``--project-dir`` flag.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


def resolve_project_dir() -> Path | None:
    """Return the ``--project-dir`` override if the current Click context
    has one, else ``None``. Safe to call outside a Click context (returns
    ``None``)."""
    try:
        ctx = click.get_current_context(silent=True)
    except RuntimeError:
        return None
    if ctx is None or not isinstance(getattr(ctx, "obj", None), dict):
        return None
    from cataforge.interface.cli.main import CTX_PROJECT_DIR

    override = ctx.obj.get(CTX_PROJECT_DIR)
    return Path(override) if override else None


def get_config_manager() -> ConfigManager:
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


def root_relative_default(
    ctx: click.Context,
    param_name: str,
    value: Any,
    *,
    rel: Path | None = None,
) -> Any:
    """Honour the global ``--project-dir`` for a per-command path option whose
    default is project-relative (e.g. ``--db-path`` defaulting to
    ``.cataforge/kg/store``, ``--project-root`` defaulting to ``.``).

    The ``docs`` / ``kg`` command groups predate the ``resolve_root`` helper:
    they carry their own ``--project-root`` / ``--db-path`` options and resolve
    relative defaults against the process cwd, so they silently ignored the
    global ``--project-dir``. This routes the global flag through *only* when
    the option fell back to its default.

    Precedence: an explicitly-passed value always wins; otherwise, when
    ``--project-dir`` is set and the option was defaulted, the project-relative
    default is re-rooted under the override. When ``--project-dir`` is unset the
    value is returned unchanged, preserving cwd-relative behaviour.

    ``rel`` is the project-relative suffix appended under the override for a
    defaulted path (e.g. ``KG_STORE_REL`` for ``--db-path``); ``None`` returns
    the override itself (for ``--project-root``-style options).
    """
    override = resolve_project_dir()
    if override is None:
        return value
    from click.core import ParameterSource

    source = ctx.get_parameter_source(param_name)
    if source is not None and source is not ParameterSource.DEFAULT:
        return value
    return override if rel is None else override / rel


def emit_hint(message: str) -> None:
    """Print a dim hint line on stderr (used after empty-result banners)."""
    click.secho(message, fg="bright_black", err=True)


def classify_tallies(classified: Iterable[tuple[Any, str]]) -> Counter[str]:
    """Tally the *status* component of a ``classify_scaffold_files`` result.

    Both ``bootstrap`` and ``upgrade`` open-coded the same loop:

    ```python
    tallies: dict[str, int] = {}
    for _, status in classified:
        tallies[status] = tallies.get(status, 0) + 1
    ```

    ``Counter`` collapses that into a single expression and gives
    ``most_common`` / arithmetic for free. The accepted-status set
    (``update`` / ``user-modified`` / ``drift`` / ``new`` / ``ok`` etc.)
    is enforced by the upstream classifier, not by this helper — we
    just tally whatever statuses arrive.
    """
    return Counter(status for _, status in classified)


__all__ = [
    "classify_tallies",
    "emit_hint",
    "get_config_manager",
    "resolve_project_dir",
    "resolve_root",
    "root_relative_default",
]
