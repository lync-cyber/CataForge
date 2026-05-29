"""CataForge knowledge graph package.

Primary entry point is the `KnowledgeGraph` facade (query / trace /
write-lock-guarded transaction). Read/CLI callers go through the facade and
its typed sub-APIs; the low-level `KnowledgeGraphStore` (in the internal
`_store` module) and `init_store` remain available for store creation and
ingest paths that operate on the raw pyoxigraph store.
"""

from __future__ import annotations

from cataforge.domain.kg._ask import ask
from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._errors import (
    KGEntityNotFoundError,
    KGError,
    KGStoreAlreadyExistsError,
    KGStoreNotInitializedError,
    KGValidationError,
)
from cataforge.domain.kg._store import (
    KnowledgeGraphStore,
    bootstrap_subclass_axioms,
    init_store,
)
from cataforge.domain.kg.export.render import render_entity
from cataforge.domain.kg.facade import KnowledgeGraph, open_store
from cataforge.domain.kg.query import QueryAPI
from cataforge.domain.kg.trace import TraceAPI
from cataforge.domain.kg.transaction import TransactionContext

__all__ = [
    "KGConfig",
    "KGEntityNotFoundError",
    "KGError",
    "KGStoreAlreadyExistsError",
    "KGStoreNotInitializedError",
    "KGValidationError",
    "KnowledgeGraph",
    "KnowledgeGraphStore",
    "QueryAPI",
    "render_entity",
    "TraceAPI",
    "TransactionContext",
    "ask",
    "bootstrap_subclass_axioms",
    "init_store",
    "open_store",
]
