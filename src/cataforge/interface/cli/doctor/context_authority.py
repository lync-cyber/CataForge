"""Doctor gate — ``context.mode`` config validity.

A project declares its single source-of-truth axis via ``context.mode``
(``markdown`` / ``graph``). This gate fails an invalid value and
fails the retired ``context.strategy`` / ``context.authoring`` pair so a
project carrying the old two-axis schema is told to migrate to ``context.mode``
(``cataforge upgrade apply`` rewrites it) rather than running silently on
the ``graph`` default.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import click

from cataforge.domain.kg._dispatch import MODES

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager

_RETIRED_KEYS = ("strategy", "authoring")


def check_context_mode_validity(cfg: ConfigManager) -> int:
    """Validate ``context.mode`` and reject the retired schema. Returns failures."""
    path = cfg.paths.framework_json
    if not path.is_file():
        click.echo("  (no framework.json — skipped)")
        return 0
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        click.echo(f"  WARN: cannot read framework.json: {exc}", err=True)
        return 0

    context = data.get("context") or {}

    retired = [k for k in _RETIRED_KEYS if k in context]
    if retired:
        click.echo(
            f"  FAIL: framework.json carries retired context.{{{', '.join(retired)}}} — "
            "the strategy/authoring pair is replaced by a single context.mode "
            "(markdown | graph). Run `cataforge upgrade apply` to migrate.",
            err=True,
        )
        return 1

    mode = context.get("mode")
    if mode is not None and mode not in MODES:
        click.echo(
            f"  FAIL: context.mode {mode!r} is invalid — expected one of {sorted(MODES)}.",
            err=True,
        )
        return 1

    click.echo("  OK: context.mode is valid")
    return 0
