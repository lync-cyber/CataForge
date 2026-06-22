"""cataforge kg — knowledge graph store lifecycle.

Command families (one module each):
- store:  init, snapshot, rollback, repair
- ingest: import, export, validate, drift-check, compare-read
- query:  query, trace
- schema: schema-context
- write:  add, update, delete
"""

from __future__ import annotations

from cataforge.interface.cli.main import cli


@cli.group("kg")
def kg_group() -> None:
    """Knowledge graph store management."""


from . import ingest, query, schema, store, write  # noqa: E402,F401
