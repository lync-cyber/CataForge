"""Doctor gate — context.strategy / context.authoring config validity.

``authoring_mode`` silently coerces an out-of-range authoring value (and
honours ``graph`` only under ``kg-first``), so a mis-declared framework.json
would otherwise run as Markdown-first without the author noticing. This gate
surfaces the contradiction at diagnostic time.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import click

from cataforge.domain.kg._dispatch import AUTHORING_MODES, CONTEXT_STRATEGIES

if TYPE_CHECKING:
    from cataforge.core.config import ConfigManager


def check_context_authority_config(cfg: ConfigManager) -> int:
    """Validate the context strategy/authoring pair. Returns the failure count."""
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
    strategy = context.get("strategy")
    authoring = context.get("authoring")

    if strategy is not None and strategy not in CONTEXT_STRATEGIES:
        click.echo(
            f"  WARN: context.strategy {strategy!r} is unrecognized — "
            f"falls back to kg-first. Expected one of {sorted(CONTEXT_STRATEGIES)}.",
            err=True,
        )
    if authoring is not None and authoring not in AUTHORING_MODES:
        click.echo(
            f"  WARN: context.authoring {authoring!r} is unrecognized — "
            f"falls back to md. Expected one of {sorted(AUTHORING_MODES)}.",
            err=True,
        )

    if authoring == "graph" and strategy != "kg-first":
        click.echo(
            f'  FAIL: context.authoring = "graph" requires context.strategy = '
            f'"kg-first", but strategy resolves to {strategy or "kg-first"!r}. '
            "Graph authoring has no authority without the kg-first backend — "
            'set strategy to "kg-first" or authoring to "md".',
            err=True,
        )
        return 1

    click.echo("  OK: context strategy/authoring pair is consistent")
    return 0
