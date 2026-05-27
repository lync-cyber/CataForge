"""Shared helpers for reading pyoxigraph SPARQL query results."""
from __future__ import annotations

from typing import Any


def _term_value(term: Any) -> Any:
    if term is None:
        return None
    return getattr(term, "value", term)


def _row_lookup(row: Any, var: str) -> Any:
    """Read ``row[var]`` from a pyoxigraph ``QuerySolution`` (or a dict).

    Returns ``None`` both when the variable is unbound and when the
    variable name is not part of the projection.
    """
    try:
        return row[var]
    except (KeyError, IndexError):
        return None


def _strv(term: Any) -> str | None:
    v = _term_value(term)
    return None if v is None else str(v)
