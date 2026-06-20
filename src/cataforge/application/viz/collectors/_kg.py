"""Shared read-only KnowledgeGraph access for KG-backed collectors.

An uninitialised store degrades to a ``CataforgeError`` carrying the facade's
own ``kg init`` hint, so every KG view fails the same actionable way.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from cataforge.core.errors import CataforgeError
from cataforge.core.paths import KG_STORE_REL
from cataforge.domain.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraph


@contextmanager
def open_kg(root: Path) -> Generator[KnowledgeGraph, None, None]:
    config = KGConfig(store_backend="oxigraph", db_path=root / KG_STORE_REL)
    try:
        with KnowledgeGraph.connect(config, read_only=True) as kg:
            yield kg
    except KGStoreNotInitializedError as exc:
        raise CataforgeError(str(exc)) from exc
