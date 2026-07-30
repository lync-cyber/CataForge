"""Chokepoint for SPARQL ASK queries against pyoxigraph stores.

``pyoxigraph.Store.query("ASK { ... }")`` returns a ``QueryBoolean``
instance, not a Python ``bool``.  Direct equality comparison silently
always returns ``False``; only ``bool(...)`` yields the right answer.

Every traceability-completeness ASK in the KG layer must consume the
result through this single function.  A pre-commit grep gate enforces
this constraint under ``src/cataforge/domain/kg/``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cataforge.domain.kg.read_query import first_sparql_keyword

if TYPE_CHECKING:
    import pyoxigraph as ox


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
    if first_sparql_keyword(sparql) != "ASK":
        raise ValueError(
            "ask() only accepts ASK queries; for SELECT/CONSTRUCT/UPDATE use "
            "the typed QueryAPI surface."
        )
    result = store.query(sparql)
    return bool(result)
