"""Chokepoint for SPARQL ASK queries against pyoxigraph stores.

``pyoxigraph.Store.query("ASK { ... }")`` returns a ``QueryBoolean``
instance, not a Python ``bool``.  Direct equality comparison silently
always returns ``False``; only ``bool(...)`` yields the right answer.

Every traceability-completeness ASK in the KG layer must consume the
result through this single function.  A pre-commit grep gate enforces
this constraint under ``src/cataforge/kg/``.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pyoxigraph as ox

_SPARQL_KEYWORD_RE = re.compile(
    r"(?:#[^\n]*\n\s*)*"  # skip leading comment lines
    r"(?:(?:PREFIX|BASE)\s+\S+\s+<[^>]*>\s*)*"  # skip PREFIX/BASE prologues
    r"(\w+)",  # capture first keyword (ASK, SELECT, CONSTRUCT, …)
    re.IGNORECASE,
)


def _first_sparql_keyword(sparql: str) -> str | None:
    """Extract the first SPARQL query-form keyword, skipping comments and PREFIX declarations."""
    m = _SPARQL_KEYWORD_RE.match(sparql.lstrip())
    return m.group(1).upper() if m else None


def ask(store: ox.Store, sparql: str, bindings: dict[str, Any] | None = None) -> bool:
    """Run an ASK query and return a real Python ``bool``.

    Parameters
    ----------
    store:
        An open ``pyoxigraph.Store``.
    sparql:
        A SPARQL ASK query.  Other forms (SELECT / CONSTRUCT / UPDATE)
        are rejected up front; route those through ``QueryAPI`` instead.
    bindings:
        Reserved for future use.  Raises ``NotImplementedError`` when a
        non-empty dict is passed.
    """
    first_keyword = _first_sparql_keyword(sparql)
    if first_keyword != "ASK":
        raise ValueError(
            "ask() only accepts ASK queries; for SELECT/CONSTRUCT/UPDATE use "
            "the typed QueryAPI surface."
        )
    if bindings:
        raise NotImplementedError(
            "ask() does not yet pass through bindings; substitute server-side or "
            "interpolate before passing the SPARQL string in."
        )
    result = store.query(sparql)
    return bool(result)
