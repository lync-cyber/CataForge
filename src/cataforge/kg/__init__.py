"""CataForge knowledge graph package (0.5.0 Alpha).

Sub-PR 2 surface — minimal store lifecycle:

* `KGConfig` — connection configuration (task-5 §5.2).
* `KnowledgeGraphStore` — sync store handle wrapping `pyoxigraph.Store`.
* `init_store` / `bootstrap_subclass_axioms` — `cataforge kg init` backend.
* `ask` — SPARQL ASK chokepoint that returns a real Python `bool`
  (spike-2 §2.2, issue #142).
* `KGError` / `KGStoreNotInitializedError` / `KGStoreAlreadyExistsError`
  — exceptions raised by this layer.

The richer `KnowledgeGraph` facade with query / trace / transaction
sub-APIs (task-5 §5.2) is layered on top in subsequent sub-PRs.
"""
from __future__ import annotations

from cataforge.kg._ask import ask
from cataforge.kg._config import KGConfig
from cataforge.kg._errors import (
    KGError,
    KGStoreAlreadyExistsError,
    KGStoreNotInitializedError,
)
from cataforge.kg.store import (
    KnowledgeGraphStore,
    bootstrap_subclass_axioms,
    init_store,
)

__all__ = [
    "KGConfig",
    "KGError",
    "KGStoreAlreadyExistsError",
    "KGStoreNotInitializedError",
    "KnowledgeGraphStore",
    "ask",
    "bootstrap_subclass_axioms",
    "init_store",
]
