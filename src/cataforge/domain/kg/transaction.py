"""`TransactionContext` — write-side staging for the KnowledgeGraph facade.

Provides both low-level quad staging (`add`/`remove`) and high-level
entity CRUD (`add_entity`/`update_entity`/`delete_entity`/`add_relation`/
`remove_relation`). High-level methods build quads via `_quads.py` and
delegate to the low-level staging list; `commit()` applies them atomically.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cataforge.domain.kg._ask import ask
from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._errors import KGEntityNotFoundError, KGValidationError
from cataforge.domain.kg._quads import (
    build_entity_quads,
    build_relation_quad,
    quads_for_subject,
    quads_targeting,
)
from cataforge.domain.kg._sparql_utils import (
    assert_safe_iri,
    cf_namespace,
    escape_sparql_literal,
)
from cataforge.domain.kg.ingest.iri import entity_iri

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
    # Low-level staging API
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
    # High-level entity CRUD
    # ------------------------------------------------------------------

    def add_entity(
        self,
        entity_id: str,
        class_name: str,
        title: str,
        source_doc: str,
        source_section: str,
        content_hash: str,
        project_iri: str,
        *,
        extra_slots: dict[str, str] | None = None,
        mtime: float | None = None,
    ) -> str:
        """Stage quads for a new entity. Returns the entity IRI.

        Idempotent: if the entity already exists with the same
        content_hash, nothing is staged.
        """
        self._guard_open()
        iri = entity_iri(entity_id, self._config.base_namespace)
        ns = cf_namespace(self._config)

        if self._content_hash_matches(iri, content_hash, ns):
            return iri

        for q in quads_for_subject(self._store, iri):
            self._staged_removes.append(q)

        for q in build_entity_quads(
            entity_id,
            class_name,
            title,
            source_doc,
            source_section,
            content_hash,
            project_iri,
            self._config,
            extra_slots=extra_slots,
            mtime=mtime,
        ):
            self._staged_adds.append(q)

        return iri

    def update_entity(
        self,
        entity_id: str,
        *,
        content_hash: str | None = None,
        **slot_values: str,
    ) -> None:
        """Stage a partial update for specific slots on an existing entity."""
        self._guard_open()
        iri = entity_iri(entity_id, self._config.base_namespace)
        ns = cf_namespace(self._config)

        if not self._entity_exists(iri):
            raise KGEntityNotFoundError(f"Entity {entity_id} not found in store.")

        if content_hash is not None and self._content_hash_matches(iri, content_hash, ns):
            return

        import pyoxigraph as ox  # noqa: PLC0415

        subject = ox.NamedNode(iri)
        string_dt = ox.NamedNode("http://www.w3.org/2001/XMLSchema#string")

        for slot_name, new_value in slot_values.items():
            pred = ox.NamedNode(f"{ns}{slot_name}")
            for q in list(self._store.quads_for_pattern(subject, pred, None, None)):
                self._staged_removes.append(q)
            self._staged_adds.append(
                ox.Quad(
                    subject,
                    pred,
                    ox.Literal(new_value, datatype=string_dt),
                )
            )

        if content_hash is not None:
            pred = ox.NamedNode(f"{ns}content_hash")
            for q in list(self._store.quads_for_pattern(subject, pred, None, None)):
                self._staged_removes.append(q)
            self._staged_adds.append(
                ox.Quad(
                    subject,
                    pred,
                    ox.Literal(content_hash, datatype=string_dt),
                )
            )

        datetime_dt = ox.NamedNode("http://www.w3.org/2001/XMLSchema#dateTime")
        updated_at_pred = ox.NamedNode(f"{ns}updated_at")
        for q in list(self._store.quads_for_pattern(subject, updated_at_pred, None, None)):
            self._staged_removes.append(q)
        self._staged_adds.append(
            ox.Quad(
                subject,
                updated_at_pred,
                ox.Literal(
                    datetime.now(timezone.utc).isoformat(),
                    datatype=datetime_dt,
                ),
            )
        )

    def delete_entity(
        self,
        entity_id: str,
        *,
        cascade: bool = False,
    ) -> None:
        """Stage removal of all quads for an entity.

        With ``cascade=True``, also removes quads where this entity is the
        object (incoming edges). Without cascade, raises
        ``KGValidationError`` if incoming edges exist.
        """
        self._guard_open()
        iri = entity_iri(entity_id, self._config.base_namespace)

        if not self._entity_exists(iri):
            raise KGEntityNotFoundError(f"Entity {entity_id} not found in store.")

        incoming = quads_targeting(self._store, iri)
        if incoming and not cascade:
            raise KGValidationError(
                f"Entity {entity_id} has {len(incoming)} incoming edge(s). "
                "Use cascade=True to remove them."
            )

        if incoming:
            self._staged_removes.extend(incoming)

        for q in quads_for_subject(self._store, iri):
            self._staged_removes.append(q)

    def add_relation(
        self,
        subject_id: str,
        predicate_curie: str,
        object_id: str,
    ) -> None:
        """Stage a traceability edge. Idempotent: skips if already present."""
        self._guard_open()
        quad = build_relation_quad(subject_id, predicate_curie, object_id, self._config)
        s_iri = entity_iri(subject_id, self._config.base_namespace)
        o_iri = entity_iri(object_id, self._config.base_namespace)
        p_iri = quad.predicate.value
        if ask(
            self._store,
            f"ASK {{ <{assert_safe_iri(s_iri)}> "
            f"<{assert_safe_iri(p_iri)}> "
            f"<{assert_safe_iri(o_iri)}> }}",
        ):
            return
        self._staged_adds.append(quad)

    def remove_relation(
        self,
        subject_id: str,
        predicate_curie: str,
        object_id: str,
    ) -> None:
        """Stage removal of a traceability edge."""
        self._guard_open()
        quad = build_relation_quad(subject_id, predicate_curie, object_id, self._config)
        self._staged_removes.append(quad)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def commit(self) -> None:
        """Apply staged removes followed by adds.

        pyoxigraph exposes no native transaction, so a failure partway
        through the adds would otherwise leave the removed quads gone. The
        removed quads are restored on any exception (re-add is idempotent)
        so a mid-commit failure does not silently lose data.
        """
        if self._rolled_back:
            raise RuntimeError("Cannot commit a transaction that has already been rolled back.")
        if self._committed:
            raise RuntimeError("Transaction has already been committed.")
        removed: list = []
        try:
            for q in self._staged_removes:
                self._store.remove(q)
                removed.append(q)
            for q in self._staged_adds:
                self._store.add(q)
        except Exception:
            for q in removed:
                self._store.add(q)
            raise
        self._committed = True

    def rollback(self) -> None:
        """Discard staged changes without touching the live store."""
        if self._committed:
            raise RuntimeError("Cannot rollback a transaction that has already committed.")
        self._staged_adds.clear()
        self._staged_removes.clear()
        self._rolled_back = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _guard_open(self) -> None:
        if self._committed:
            raise RuntimeError("Transaction already committed.")
        if self._rolled_back:
            raise RuntimeError("Transaction already rolled back.")

    def _entity_exists(self, iri: str) -> bool:
        return ask(self._store, f"ASK {{ <{iri}> a ?cls }}")

    def _content_hash_matches(self, iri: str, content_hash: str, namespace: str) -> bool:
        safe_hash = escape_sparql_literal(content_hash)
        sparql = (
            f"PREFIX cf: <{namespace}> "
            f'ASK {{ <{assert_safe_iri(iri)}> cf:content_hash "{safe_hash}" }}'
        )
        return ask(self._store, sparql)


@contextmanager
def transaction(store: ox.Store, config: KGConfig) -> Generator[TransactionContext, None, None]:
    """Synchronous transaction context manager.

    Commits on clean exit, rolls back on exception.
    """
    txn = TransactionContext(store, config)
    try:
        yield txn
    except Exception as _orig_exc:
        if not txn._committed:
            try:
                txn.rollback()
            except Exception as _rb_exc:
                _orig_exc.add_note(f"rollback also failed: {_rb_exc!r}")
        raise
    else:
        if not txn._committed:
            txn.commit()


__all__ = [
    "TransactionContext",
    "transaction",
]
