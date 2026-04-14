"""Shared messaging for CLI subcommands that are not implemented yet."""

from __future__ import annotations

import click

STUB_EXIT_CODE = 2


def exit_not_implemented(feature: str, detail: str = "") -> None:
    """Print a consistent message and exit with code 2."""
    msg = f"{feature} 尚未实现。"
    if detail:
        msg = f"{msg} {detail}"
    click.secho(msg, fg="yellow", err=True)
    raise SystemExit(STUB_EXIT_CODE)
