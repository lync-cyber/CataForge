"""Chokepoint for SPARQL ASK queries against pyoxigraph stores.

``pyoxigraph.Store.query("ASK { ... }")`` returns a ``QueryBoolean``
instance, not a Python ``bool``.  Direct equality comparison silently
always returns ``False``; only ``bool(...)`` yields the right answer.

Every traceability-completeness ASK in the KG layer must consume the
result through this single function.  A pre-commit grep gate enforces
this constraint under ``src/cataforge/domain/kg/``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyoxigraph as ox

_SPARQL_KEYWORD_RE = re.compile(
    r"(?:#[^\n]*\n\s*)*"  # skip leading comment lines
    r"(?:(?:"
    r"PREFIX\s+\S+\s+<[^>]*>"  # PREFIX <local>: <iri>
    r"|"
    r"BASE\s+<[^>]*>"  # BASE <iri>  (no intermediate token)
    r")\s*)*"
    r"(\w+)",  # capture first keyword (ASK, SELECT, CONSTRUCT, …)
    re.IGNORECASE,
)


def _first_sparql_keyword(sparql: str) -> str | None:
    """Extract the first SPARQL query-form keyword, skipping comments and PREFIX declarations."""
    m = _SPARQL_KEYWORD_RE.match(sparql.lstrip())
    return m.group(1).upper() if m else None


def ask(store: ox.Store, sparql: str) -> bool:
    """Run an ASK query and return a real Python ``bool``.

    Parameters
    ----------
    store:
        An open ``pyoxigraph.Store``.
    sparql:
        A SPARQL ASK query.  Other forms (SELECT / CONSTRUCT / UPDATE)
        are rejected up front; route those through ``QueryAPI`` instead.
    """
    first_keyword = _first_sparql_keyword(sparql)
    if first_keyword != "ASK":
        raise ValueError(
            "ask() only accepts ASK queries; for SELECT/CONSTRUCT/UPDATE use "
            "the typed QueryAPI surface."
        )
    result = store.query(sparql)
    return bool(result)
