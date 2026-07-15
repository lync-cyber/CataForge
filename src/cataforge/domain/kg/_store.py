"""KG store lifecycle — open / bootstrap / close.

A thin wrapper around `pyoxigraph.Store` that opens either an in-memory or
RocksDB-backed graph and loads the packaged `rdfs:subClassOf` axioms
artifact (the LinkML `is_a` chain, materialized at codegen time).

The `KnowledgeGraph` facade (query / trace / transaction sub-APIs) is
layered on top of this primitive; this module's sole responsibility is
opening the store and bootstrapping the subclass-closure hierarchy so
SPARQL ASK queries work correctly.
"""

from __future__ import annotations

import shutil
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from cataforge.domain.kg._ask import ask
from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._errors import (
    KGStoreAlreadyExistsError,
    KGStoreNotInitializedError,
)
from cataforge.domain.kg._schema_axioms import GOVERNANCE_NS, packaged_axioms_path

if TYPE_CHECKING:
    import pyoxigraph as ox


def _open_pyoxigraph(
    config: KGConfig, *, create: bool = False, read_only: bool = False
) -> ox.Store:
    """Open the underlying pyoxigraph store per `config.store_backend`.

    `pyoxigraph` is imported lazily so callers who only need :class:`KGConfig`
    (the dataclass shipped in the base wheel) can use this package without
    the `kg` extra installed.

    With `read_only=True` an existing on-disk store is opened via
    `Store.read_only`, which performs no manifest/WAL/CURRENT rotation and
    so leaves the store directory byte-for-byte unchanged (deterministic
    snapshots, no churn from query-only callers).
    `read_only` is ignored for the memory backend and incompatible with
    `create` (a fresh store must be opened read-write to bootstrap).
    Opening read-only while another process writes the same store is
    undefined behavior; this is safe for single-process CLI invocations.
    """
    import pyoxigraph as ox  # noqa: PLC0415

    if config.store_backend == "memory":
        return ox.Store()

    db_path = config.db_path
    if db_path.exists():
        if read_only and not create:
            return ox.Store.read_only(str(db_path))
        return ox.Store(str(db_path))

    if not create:
        raise KGStoreNotInitializedError(
            f"KG store not found at {db_path}. Run `cataforge kg init` first."
        )

    db_path.mkdir(parents=True, exist_ok=True)
    return ox.Store(str(db_path))


def bootstrap_subclass_axioms(store: ox.Store, *, include_governance: bool = False) -> int:
    """Insert `rdfs:subClassOf` triples from the packaged axioms artifact.

    The artifact materializes the LinkML `is_a` chain at codegen time
    (`scripts/codegen_kg_schema.py`), so bootstrap needs no linkml stack at
    runtime. Axioms whose subject lives in the governance namespace are
    skipped unless the store is governance-enabled; subject-prefix filtering
    is exact because core and governance classes never share an `is_a` edge
    across namespaces (pinned by the schema-walk equivalence test).

    Returns the number of triples inserted. Idempotent: re-inserting an
    existing triple is a no-op at the RDF semantics layer (pyoxigraph
    deduplicates by quad identity).
    """
    import pyoxigraph as ox  # noqa: PLC0415

    path = packaged_axioms_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"packaged subclass-axioms artifact missing: {path} — "
            "the cataforge installation is incomplete; reinstall the package"
        )

    count = 0
    for quad in ox.parse(path.read_bytes(), ox.RdfFormat.TURTLE):
        if not include_governance and quad.subject.value.startswith(GOVERNANCE_NS):
            continue
        store.add(quad)
        count += 1
    return count


class KnowledgeGraphStore:
    """Minimal sync store handle.

    Wraps `pyoxigraph.Store` so callers receive a typed handle they can pass
    around without importing `pyoxigraph` directly. The underlying store is
    exposed via `.raw` for code paths (ingest / export) that legitimately
    need pyoxigraph APIs beyond the wrapper's typed surface.
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
        return bootstrap_subclass_axioms(self._store, include_governance=self._config.governance)

    def close(self) -> None:
        # pyoxigraph 0.5.x has no explicit close on Store; resources release
        # on GC. Method exists so callers and future async wrappers have a
        # stable shutdown hook.
        return None

    @classmethod
    @contextmanager
    def connect(
        cls, config: KGConfig, *, read_only: bool = False
    ) -> Generator[KnowledgeGraphStore, None, None]:
        """Open an existing store; raise if the on-disk path is missing."""
        store = _open_pyoxigraph(config, create=False, read_only=read_only)
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
                f"KG store already exists at {config.db_path}. Pass --force to overwrite."
            )
        shutil.rmtree(config.db_path)

    store = _open_pyoxigraph(config, create=True)
    handle = KnowledgeGraphStore(store, config)
    handle.bootstrap_subclass_axioms()
    return handle
