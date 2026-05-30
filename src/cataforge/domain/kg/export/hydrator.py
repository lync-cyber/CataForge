"""Collapse SPARQL multi-row results into one render context per entity.

A pyoxigraph `SELECT` row is a `dict[str, Term | None]` where every
`OPTIONAL` block fans the same subject across multiple rows. The
hydrator deduplicates scalar fields (first non-null wins) and
aggregates multi-valued fields keyed on a sort-stable composite.

The output is a plain dict consumed by Jinja2. Pydantic context objects
are used when SHACL / governance validation is active.
"""
from __future__ import annotations

from typing import Any

from cataforge.domain.kg._sparql_utils import _row_lookup, _term_value

_SCALAR_FIELDS = (
    "entity_id",
    "sort_key",
    "title",
    "description",
    "status",
    "priority",
    "content_hash",
    "source_doc",
    "source_section",
    "authored_by",
    "expected_result",
    "test_result",
    "narrative_body",
    "ui_route",
    "layout_spec",
    "task_status",
)


def hydrate_rows(
    rows: list[Any],
    relation_groups: dict[str, tuple[str, ...]],
) -> dict[str, Any] | None:
    """Fold SPARQL rows into one render context dict.

    `relation_groups` is `{group_name: (id_var, sort_key_var, title_var, ...)}`.
    Each group becomes `entity[group_name]` — a list of dicts ordered by
    `(sort_key, entity_id)` so re-renders are byte-stable even if SPARQL
    join order drifts.
    """
    if not rows:
        return None

    # Pre-populate every scalar to None so Jinja2 `StrictUndefined`
    # only fires on truly unknown attributes (typos / template drift),
    # not on optional slots the SPARQL OPTIONAL block left unbound.
    context: dict[str, Any] = {field: None for field in _SCALAR_FIELDS}

    for row in rows:
        for scalar in _SCALAR_FIELDS:
            if context[scalar] is not None:
                continue
            value = _term_value(_row_lookup(row, scalar))
            if value is not None:
                context[scalar] = value

    for group_name, vars_tuple in relation_groups.items():
        id_var = vars_tuple[0]
        bucket: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            id_val = _term_value(_row_lookup(row, id_var))
            if id_val is None:
                continue
            sort_var = vars_tuple[1] if len(vars_tuple) > 1 else id_var
            sort_val = _term_value(_row_lookup(row, sort_var)) or ""
            key = (str(sort_val), str(id_val))
            if key in bucket:
                continue
            entry: dict[str, Any] = {"entity_id": id_val, "sort_key": sort_val}
            for var in vars_tuple[2:]:
                entry[var] = _term_value(_row_lookup(row, var))
            bucket[key] = entry
        context[group_name] = [bucket[k] for k in sorted(bucket.keys())]

    return context
