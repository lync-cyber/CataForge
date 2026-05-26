"""`TransactionContext` — write-side staging for the KnowledgeGraph facade.

Sub-PR 5 ships a minimal synchronous variant: callers can stage quads
in a list, commit them in one batch, or discard them on exception.
SHACL post-validation and optimistic-lock retries (task-5 §5.2 full
spec) arrive in a later sub-PR.

The shape is deliberately compatible with the spec's `async with
kg.transaction() as txn:` pattern — :meth:`KnowledgeGraph.transaction`
adapts this sync context with `asyncio.Lock` + `asyncio.to_thread`.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from cataforge.kg._config import KGConfig

if TYPE_CHECKING:
    import pyoxigraph as ox


class TransactionContext:
    """Write-side context: stage quads, commit atomically, or rollback.

    Use via :meth:`KnowledgeGraph.transaction` rather than constructing
    directly — the facade wraps this with the project-wide write lock.
    """

    def __init__(self, store: ox.Store, config: KGConfig) -> None:
        self._store = store
        self._config = config
        self._staged_adds: list[ox.Quad] = []
        self._staged_removes: list[ox.Quad] = []
        self._committed = False
        self._rolled_back = False

    # ------------------------------------------------------------------
    # Staging API
    # ------------------------------------------------------------------

    def add(self, quad: ox.Quad) -> None:
        """Stage a quad for insertion at commit time."""
        self._guard_open()
        self._staged_adds.append(quad)

    def remove(self, quad: ox.Quad) -> None:
        """Stage a quad for removal at commit time."""
        self._guard_open()
        self._staged_removes.append(quad)

    @property
    def pending_inserts(self) -> int:
        return len(self._staged_adds)

    @property
    def pending_deletes(self) -> int:
        return len(self._staged_removes)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def commit(self) -> None:
        """Apply staged removes followed by adds. Idempotent on re-call."""
        if self._committed or self._rolled_back:
            return
        for q in self._staged_removes:
            self._store.remove(q)
        for q in self._staged_adds:
            self._store.add(q)
        self._committed = True

    def rollback(self) -> None:
        """Discard staged changes without touching the live store."""
        if self._committed:
            raise RuntimeError(
                "Cannot rollback a transaction that has already committed."
            )
        self._staged_adds.clear()
        self._staged_removes.clear()
        self._rolled_back = True

    def _guard_open(self) -> None:
        if self._committed:
            raise RuntimeError("Transaction already committed.")
        if self._rolled_back:
            raise RuntimeError("Transaction already rolled back.")


@contextmanager
def transaction(store: ox.Store, config: KGConfig) -> Iterator[TransactionContext]:
    """Synchronous transaction context manager.

    Commits on clean exit, rolls back on exception. Designed for use
    inside :meth:`KnowledgeGraph.transaction` which adds the asyncio
    write-lock guard required by task-5 §5.2.
    """
    txn = TransactionContext(store, config)
    try:
        yield txn
    except Exception:
        txn.rollback()
        raise
    else:
        txn.commit()


__all__ = [
    "TransactionContext",
    "transaction",
]
