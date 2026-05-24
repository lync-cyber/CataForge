"""``cataforge kg`` — knowledge-graph CLI surface.

This module defines the top-level ``kg`` group and its ``adapter``
subgroup, then triggers side-effect imports of the three subcommand
packages (``query``, ``ingest``, ``crud``) so their Click decorators
register on this group at startup.

Subcommand layout:

* :mod:`cataforge.cli.kg.query`  — read-only commands (query, validate,
  conflicts, resolve, coverage, infer, impact, explain, viz)
* :mod:`cataforge.cli.kg.ingest` — content → graph (migrate, ingest,
  export, render, template-lint, benchmark)
* :mod:`cataforge.cli.kg.crud`   — store mutations (init, add/update/
  delete entity, add/remove relation, adapter subgroup)

See ``docs/research/kg-feature-upgrade-design.md`` for the full design.
"""

from __future__ import annotations

from cataforge.cli.main import cli


@cli.group("kg")
def kg_group() -> None:
    """Knowledge-graph store, query, render, validate, and benchmark.

    See ``docs/research/kg-feature-upgrade-design.md`` for the full design.
    """


@kg_group.group("adapter")
def kg_adapter_group() -> None:
    """List, inspect, and dispatch KG adapters (design §3)."""


# Side-effect imports: each module decorates ``kg_group`` /
# ``kg_adapter_group`` with its commands at import time. The order is
# arbitrary; Click resolves the resulting --help layout alphabetically.
# noqa: E402, F401 — must follow the group definitions above.
from cataforge.cli.kg import crud as _crud  # noqa: E402, F401
from cataforge.cli.kg import ingest as _ingest  # noqa: E402, F401
from cataforge.cli.kg import query as _query  # noqa: E402, F401
