"""Shared Click option factories for the ``cataforge kg`` command family.

The ``--db-path`` option was inline-duplicated across every kg subcommand,
with the ``exists=`` constraint drifting between read-only and write commands.
These factories give read-only commands (query, trace, validate, …) a single
``exists=True`` policy and write/create commands (init, import, …) an
``exists=False`` policy, so the constraint can no longer drift per command.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import click
from click.decorators import FC

from cataforge.core.paths import KG_STORE_REL

_DB_PATH_HELP = "Filesystem path of the RocksDB-backed Oxigraph store."


def db_path_option(*, exists: bool = False) -> Callable[[FC], FC]:
    """``--db-path`` for commands that may create the store (init, import).

    ``exists=False`` lets the path be materialized by the command itself.
    """
    return click.option(
        "--db-path",
        type=click.Path(exists=exists, file_okay=False, dir_okay=True, path_type=Path),
        default=KG_STORE_REL,
        show_default=True,
        help=_DB_PATH_HELP,
    )


def db_path_ro_option() -> Callable[[FC], FC]:
    """``--db-path`` for read-only commands (query, trace, validate, …).

    The store must already exist, so ``exists=True`` rejects a missing path
    at parse time with a uniform Click error across every read-only command.
    """
    return db_path_option(exists=True)
