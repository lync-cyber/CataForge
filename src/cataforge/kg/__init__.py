"""CataForge knowledge graph package (0.5.0 Alpha).

Public surface:

* `KGConfig` — connection configuration (task-5 §5.2).
* `KnowledgeGraph` — read+write facade exposing `query`, `trace`, and a
  synchronous `transaction()` context manager.
* `KnowledgeGraphStore` — low-level sync store handle wrapping
  `pyoxigraph.Store` (used by ingest / migrate scripts).
* `QueryAPI` / `TraceAPI` / `TransactionContext` — sub-API classes.
* `init_store` / `bootstrap_subclass_axioms` — `cataforge kg init` backend.
* `ask` — SPARQL ASK chokepoint that returns a real Python `bool`
  (spike-2 §2.2, issue #142).
* `KGError` / `KGStoreNotInitializedError` / `KGStoreAlreadyExistsError`
  — exceptions raised by this layer.
"""
from __future__ import annotations

from cataforge.kg._ask import ask
from cataforge.kg._config import KGConfig
from cataforge.kg._errors import (
    KGError,
    KGStoreAlreadyExistsError,
    KGStoreNotInitializedError,
)
from cataforge.kg.facade import KnowledgeGraph
from cataforge.kg.query import QueryAPI
from cataforge.kg.store import (
    KnowledgeGraphStore,
    bootstrap_subclass_axioms,
    init_store,
)
from cataforge.kg.trace import TraceAPI
from cataforge.kg.transaction import TransactionContext

__all__ = [
    "KGConfig",
    "KGError",
    "KGStoreAlreadyExistsError",
    "KGStoreNotInitializedError",
    "KnowledgeGraph",
    "KnowledgeGraphStore",
    "QueryAPI",
    "TraceAPI",
    "TransactionContext",
    "ask",
    "bootstrap_subclass_axioms",
    "init_store",
]
