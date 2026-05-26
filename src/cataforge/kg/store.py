"""KG store lifecycle — open / bootstrap / close.

Sub-PR 2 deliberately ships a minimal surface: a thin wrapper around
`pyoxigraph.Store` that knows how to open either an in-memory or
RocksDB-backed graph and how to materialize the LinkML `is_a` chain as
`rdfs:subClassOf` triples (spike-2 §2.1, issue #142).

The full `KnowledgeGraph` facade described in task-5 §5.2 (query / trace /
transaction sub-APIs) is layered on top of this primitive in later
sub-PRs; sub-PR 2's sole job is "you can open an empty store, the
subclass-closure hierarchy is loaded, and SPARQL ASK works correctly".
"""
from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager

import pyoxigraph as ox

from cataforge.kg._ask import ask
from cataforge.kg._config import KGConfig
from cataforge.kg._errors import (
    KGStoreAlreadyExistsError,
    KGStoreNotInitializedError,
)
from cataforge.kg._schema_axioms import (
    RDFS_SUBCLASSOF_IRI,
    expand_curie,
    iter_subclass_axioms,
    prefix_map,
)


def _open_pyoxigraph(config: KGConfig, *, create: bool = False) -> ox.Store:
    """Open the underlying pyoxigraph store per `config.store_backend`."""
    if config.store_backend == "memory":
        return ox.Store()

    db_path = config.db_path
    if db_path.exists():
        return ox.Store(str(db_path))

    if not create:
        raise KGStoreNotInitializedError(
            f"KG store not found at {db_path}. Run `cataforge kg init` first."
        )

    db_path.mkdir(parents=True, exist_ok=True)
    return ox.Store(str(db_path))


def bootstrap_subclass_axioms(
    store: ox.Store, *, include_governance: bool = False
) -> int:
    """Insert `rdfs:subClassOf` triples derived from the LinkML `is_a` chain.

    Returns the number of triples inserted. Idempotent: re-inserting an
    existing triple is a no-op at the RDF semantics layer (pyoxigraph
    deduplicates by quad identity).
    """
    prefixes = prefix_map(include_governance=include_governance)
    subclassof = ox.NamedNode(RDFS_SUBCLASSOF_IRI)

    count = 0
    for child_curie, parent_curie in iter_subclass_axioms(
        include_governance=include_governance
    ):
        child_iri = expand_curie(child_curie, prefixes)
        parent_iri = expand_curie(parent_curie, prefixes)
        store.add(
            ox.Quad(
                ox.NamedNode(child_iri),
                subclassof,
                ox.NamedNode(parent_iri),
            )
        )
        count += 1
    return count


class KnowledgeGraphStore:
    """Minimal sync store handle for sub-PR 2.

    Wraps `pyoxigraph.Store` so callers receive a typed handle they can pass
    around without importing `pyoxigraph` directly. The underlying store is
    exposed via `.raw` for code paths (ingest / export) that legitimately
    need to call pyoxigraph APIs the wrapper does not yet surface.
    """

    def __init__(self, store: ox.Store, config: KGConfig) -> None:
        self._store = store
        self._config = config

    @property
    def raw(self) -> ox.Store:
        return self._store

    @property
    def config(self) -> KGConfig:
        return self._config

    def ask(self, sparql: str) -> bool:
        """Run a SPARQL ASK query through the `_ask.ask()` chokepoint."""
        return ask(self._store, sparql)

    def bootstrap_subclass_axioms(self) -> int:
        return bootstrap_subclass_axioms(
            self._store, include_governance=self._config.governance
        )

    def close(self) -> None:
        # pyoxigraph 0.5.x has no explicit close on Store; resources release
        # on GC. Method exists so callers and future async wrappers have a
        # stable shutdown hook.
        return None

    @classmethod
    @contextmanager
    def connect(cls, config: KGConfig) -> Iterator[KnowledgeGraphStore]:
        """Open an existing store; raise if the on-disk path is missing."""
        store = _open_pyoxigraph(config, create=False)
        handle = cls(store, config)
        try:
            yield handle
        finally:
            handle.close()


def init_store(config: KGConfig, *, force: bool = False) -> KnowledgeGraphStore:
    """Create the store and load bootstrap triples. Returns an open handle.

    Behavioral contract for `cataforge kg init`:

    * Memory backend → always succeeds; `force` is ignored.
    * Oxigraph backend → refuses to overwrite unless `force=True`.
    * After creation, `rdfs:subClassOf` triples are loaded so subclass-closure
      queries (`a/rdfs:subClassOf*`) work without external entailment.
    """
    if (
        config.store_backend == "oxigraph"
        and config.db_path.exists()
        and any(config.db_path.iterdir())
    ):
        if not force:
            raise KGStoreAlreadyExistsError(
                f"KG store already exists at {config.db_path}. "
                "Pass --force to overwrite."
            )
        shutil.rmtree(config.db_path)

    store = _open_pyoxigraph(config, create=True)
    handle = KnowledgeGraphStore(store, config)
    handle.bootstrap_subclass_axioms()
    return handle
