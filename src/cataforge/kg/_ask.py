"""Chokepoint for SPARQL ASK queries against pyoxigraph stores.

`pyoxigraph.Store.query("ASK { ... }")` returns a `QueryBoolean` instance,
not a Python `bool`. Comparing it with `== True` silently always returns
False even when the answer is True; only `bool(...)` (or implicit truthiness
in `if` / `while`) yields the right answer. Spike-2 §2.2, issue #142.

Every traceability-completeness ASK in the KG layer (Task 5 §5.4 trace
break, Task 6 §6.4 A13 bidirectional-coverage rewrite, doctor's
`kg_ingestion_completeness` gate) must consume the result through this
single function. A pre-commit grep gate forbids `.query(... ASK ...) == True`
patterns under `src/cataforge/kg/`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pyoxigraph as ox


def ask(store: ox.Store, sparql: str, bindings: dict[str, Any] | None = None) -> bool:
    """Run an ASK query and return a real Python `bool`.

    Parameters
    ----------
    store:
        An open `pyoxigraph.Store`. Sub-PR 2 only opens stores via
        `cataforge.kg.store.open_store(config)`; direct callers are
        responsible for lifecycle.
    sparql:
        A SPARQL ASK query. Other forms (SELECT / CONSTRUCT / UPDATE) are
        rejected up front; route those through `QueryAPI` instead.
    bindings:
        Reserved for future use. pyoxigraph 0.5.x does not expose a
        parameter-bindings hook on `Store.query` outside of `INSERT`; for
        now this is a placeholder so callers can pre-thread bindings
        through without later rewriting their call sites.
    """
    stripped = sparql.lstrip().upper()
    if not stripped.startswith("ASK") and "ASK" not in stripped.split("\n")[0].upper():
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
