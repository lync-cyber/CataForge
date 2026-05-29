"""`KnowledgeGraph` — top-level facade that binds query / trace / txn.

Provides a synchronous facade with a write-lock-guarded transaction
context manager. The write lock serializes concurrent transactions on
the same facade instance.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from cataforge.kg._config import KGConfig
from cataforge.kg._store import _open_pyoxigraph
from cataforge.kg.query import QueryAPI
from cataforge.kg.trace import TraceAPI
from cataforge.kg.transaction import TransactionContext, transaction

if TYPE_CHECKING:
    import pyoxigraph as ox


def open_store(path: Path, *, read_only: bool = False) -> ox.Store:
    """Open an existing on-disk pyoxigraph store at *path*.

    *read_only* is accepted for forward compatibility; pyoxigraph 0.5.x
    does not enforce read-only at the store level.
    """
    cfg = KGConfig(db_path=Path(path))
    return _open_pyoxigraph(cfg, create=False)


class KnowledgeGraph:
    """Synchronous facade over an open pyoxigraph store.

    Usage::

        with KnowledgeGraph.connect(config) as kg:
            feature = kg.query.feature("F-001")
            coverage = kg.trace.coverage("F-001")
            with kg.transaction() as txn:
                txn.add_entity(...)

    The facade does not own the store lifecycle by default — instances
    constructed directly take a borrowed `ox.Store` reference. The
    :meth:`connect` classmethod is the standard entry point and handles
    open/close itself.
    """

    def __init__(self, store: ox.Store, config: KGConfig) -> None:
        self._store = store
        self._config = config
        self._write_lock = threading.Lock()
        self.query = QueryAPI(store, config)
        self.trace = TraceAPI(store, config)

    @property
    def store(self) -> ox.Store:
        """Underlying `pyoxigraph.Store`. Use sparingly — prefer the
        typed sub-APIs.
        """
        return self._store

    @property
    def config(self) -> KGConfig:
        return self._config

    @classmethod
    @contextmanager
    def connect(cls, config: KGConfig) -> Iterator[KnowledgeGraph]:
        """Open an existing store on `config.db_path` and return a facade.

        The store is opened read-only-by-convention; writes still work
        but should always go through :meth:`transaction`. Lifecycle
        guarantees match :class:`cataforge.kg._store.KnowledgeGraphStore`
        (no explicit close in pyoxigraph 0.5.x).
        """
        store = _open_pyoxigraph(config, create=False)
        try:
            yield cls(store, config)
        except Exception:
            raise

    @contextmanager
    def transaction(self) -> Iterator[TransactionContext]:
        """Open a write-lock-guarded synchronous transaction.

        Commits on clean exit, rolls back on exception. The write lock
        serializes concurrent callers on the same facade instance.
        """
        with self._write_lock, transaction(self._store, self._config) as txn:
            yield txn


__all__ = ["KnowledgeGraph", "open_store"]
