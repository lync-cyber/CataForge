"""CLI error-rendering adapter.

Framework errors are defined in :mod:`cataforge.core.errors` as pure
exceptions with no Click dependency. :class:`CataforgeGroup` is the top-level
Click group: it catches a :class:`CataforgeError` raised anywhere in the
command tree and re-raises it as a :class:`click.ClickException` so Click's
own machinery renders ``Error: <msg>`` on stderr and exits with the error's
``exit_code``. Because every subcommand propagates up to this group, the
catch only needs to live here.
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
            rendered = click.ClickException(str(err))
            rendered.exit_code = err.exit_code
            raise rendered from err
