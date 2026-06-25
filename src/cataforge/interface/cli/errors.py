"""CLI error-rendering adapter.

Framework errors are defined in :mod:`cataforge.core.errors` as pure
exceptions with no Click dependency. :class:`CataforgeGroup` is the top-level
Click group: it catches a :class:`CataforgeError` raised anywhere in the
command tree, renders ``Error: <msg>`` on stderr the way Click does, and
exits with the error's ``exit_code``. Because every subcommand propagates up
to this group, the catch only needs to live here.
"""

from __future__ import annotations

import click

from cataforge.core.errors import CataforgeError


class CataforgeGroup(click.Group):
    """Top-level group that renders :class:`CataforgeError` like Click does."""

    def invoke(self, ctx: click.Context) -> object:
        try:
            return super().invoke(ctx)
        except CataforgeError as err:
            # Render + exit here instead of re-raising a ClickException subclass:
            # carrying a per-instance exit_code clashes with Click's ClassVar typing.
            click.echo(f"Error: {err}", err=True)
            ctx.exit(err.exit_code)
