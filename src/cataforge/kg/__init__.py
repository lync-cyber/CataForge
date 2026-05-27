"""CataForge knowledge graph package.

Public surface: `KnowledgeGraph` facade (query / trace / transaction),
`KGConfig`, `KnowledgeGraphStore`, `init_store`, `ask`, and the KG
exception hierarchy.
"""
from __future__ import annotations

from cataforge.kg._ask import ask
from cataforge.kg._config import KGConfig
from cataforge.kg._errors import (
    KGEntityNotFoundError,
    KGError,
    KGStoreAlreadyExistsError,
    KGStoreNotInitializedError,
    KGValidationError,
)
from cataforge.kg.export.render import render_entity
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
]
