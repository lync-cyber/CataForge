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


class _RenderedError(click.ClickException):
    """A :class:`click.ClickException` carrying a caller-chosen ``exit_code``.

    Declaring ``exit_code`` as an instance attribute here keeps the assignment
    off Click's class-level attribute, which some Click versions type as a
    class variable (assigning to that via an instance is a type error).
    """

    exit_code: int

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class CataforgeGroup(click.Group):
    """Top-level group that renders :class:`CataforgeError` like Click does."""

    def invoke(self, ctx: click.Context) -> object:
        try:
            return super().invoke(ctx)
        except CataforgeError as err:
            raise _RenderedError(str(err), err.exit_code) from err
