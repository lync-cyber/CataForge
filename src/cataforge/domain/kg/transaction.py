"""`TransactionContext` — write-side staging for the KnowledgeGraph facade.

Provides both low-level quad staging (`add`/`remove`) and high-level
entity CRUD (`add_entity`/`update_entity`/`delete_entity`/`add_relation`/
`remove_relation`). High-level methods build quads via `_quads.py` and
delegate to the low-level staging list; `commit()` applies them atomically.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from cataforge.domain.kg._ask import ask
from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._errors import KGEntityNotFoundError, KGValidationError
from cataforge.domain.kg._quads import (
    build_document_quads,
    build_entity_quads,
    build_relation_quad,
    build_section_quads,
    quads_for_subject,
    quads_targeting,
)
from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _strv,
    assert_safe_iri,
    cf_namespace,
    escape_sparql_literal,
    select_rows,
)
from cataforge.domain.kg.ingest.iri import (
    document_iri,
    entity_iri,
    resolve_entity_iri,
    section_iri,
    subordinate_entity_iri,
)

if TYPE_CHECKING:
    import pyoxigraph as ox

    from cataforge.domain.kg.ingest.structure_extract import ExtractedDocument


def _delete_target_iri(entity_id: str, base_namespace: str) -> tuple[str, str]:
    """Resolve a delete-target id to ``(form, iri)`` by its shape.

    ``http(s)://…`` → used verbatim; ``doc/{doc_id}/sec/{anchor}`` or
    ``{doc_id}/sec/{anchor}`` → Section IRI; ``doc/{doc_id}`` → Document
    IRI; ``{parent_id}/{entity_id}`` → parent-scoped subordinate IRI;
    anything else → flat entity IRI.
    """
    try:
        if entity_id.startswith(("http://", "https://")):
            return "absolute", assert_safe_iri(entity_id)
        if entity_id.startswith("doc/") or "/sec/" in entity_id:
            structural = entity_id.removeprefix("doc/")
            if "/sec/" in structural:
                doc_id, anchor = structural.split("/sec/", 1)
                return "section", section_iri(doc_id, anchor, base_namespace)
            return "document", document_iri(structural, base_namespace)
        if "/" in entity_id:
            parent_id, child_id = entity_id.split("/", 1)
            return "subordinate", subordinate_entity_iri(parent_id, child_id, base_namespace)
        return "entity", entity_iri(entity_id, base_namespace)
    except ValueError as exc:
        raise KGValidationError(f"Cannot resolve id {entity_id!r}: {exc}") from exc


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

    @property
    def store(self) -> ox.Store:
        """The underlying store, for read-side planning within the transaction."""
        return self._store

    @property
    def config(self) -> KGConfig:
        return self._config

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
        parent_id: str | None = None,
        extra_slots: dict[str, str] | None = None,
        mtime: float | None = None,
    ) -> str:
        """Stage quads for a new entity. Returns the entity IRI.

        A subordinate-class entity with ``parent_id`` set gets a parent-scoped
        IRI and a ``cf:part_of`` edge. Idempotent: if the entity already exists
        with the same content_hash, nothing is staged.
        """
        self._guard_open()
        iri = resolve_entity_iri(entity_id, class_name, parent_id, self._config.base_namespace)
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
            parent_id=parent_id,
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
                    datetime.now(UTC).isoformat(),
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
        """Stage removal of all quads for a node.

        ``entity_id`` accepts a flat entity id, a ``parent/sub`` subordinate
        id, a structural id (``doc/{doc_id}`` / ``doc/{doc_id}/sec/{anchor}``),
        or a full http(s) IRI. With ``cascade=True``, also removes quads where
        this node is the object (incoming edges). Without cascade, raises
        ``KGValidationError`` if incoming edges exist.
        """
        self._guard_open()
        form, iri = _delete_target_iri(entity_id, self._config.base_namespace)

        if not self._entity_exists(iri):
            raise KGEntityNotFoundError(
                f"Entity {entity_id} not found in store (resolved as {form} IRI <{iri}>)."
            )

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
        *,
        subject_iri: str | None = None,
        object_iri: str | None = None,
    ) -> None:
        """Stage a traceability edge. Idempotent: skips if already present.

        ``subject_iri`` / ``object_iri`` override the flat-IRI derivation so an
        edge can point at a parent-scoped subordinate node.
        """
        self._guard_open()
        quad = build_relation_quad(
            subject_id,
            predicate_curie,
            object_id,
            self._config,
            subject_iri=subject_iri,
            object_iri=object_iri,
        )
        s_iri = subject_iri or entity_iri(subject_id, self._config.base_namespace)
        o_iri = object_iri or entity_iri(object_id, self._config.base_namespace)
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

    def add_document(
        self,
        document: ExtractedDocument,
    ) -> str:
        """Stage a Document structural node from an ``ExtractedDocument``.

        Idempotent on ``content_hash``; replaces the node's quads otherwise.
        Returns the Document IRI.
        """
        self._guard_open()
        iri = document_iri(document.doc_id, self._config.base_namespace)
        ns = cf_namespace(self._config)
        if self._content_hash_matches(iri, document.content_hash, ns):
            return iri
        for q in quads_for_subject(self._store, iri):
            self._staged_removes.append(q)
        for q in build_document_quads(
            document.doc_id,
            document.doc_type,
            document.title,
            document.source_doc,
            document.content_hash,
            self._config,
            section_anchors=document.section_anchors,
            version=document.version,
            status=document.status,
            frontmatter_raw=document.frontmatter_raw,
            preamble_body=document.preamble_body,
            source_path=document.source_path,
        ):
            self._staged_adds.append(q)
        return iri

    def add_section(
        self,
        doc_id: str,
        anchor: str,
        narrative_body: str,
        content_hash: str,
        *,
        position: int | None = None,
        level: int | None = None,
        title: str | None = None,
        contained_entity_ids: list[str] | None = None,
    ) -> str:
        """Stage a Section node carrying ``narrative_body``. Returns its IRI.

        Idempotent on ``content_hash``; replaces the node's quads otherwise.
        When ``position`` / ``level`` are omitted the document order is
        preserved: an existing Section keeps its stored ``cf:position`` /
        ``cf:section_level``; a new Section appends after the document's
        current last section (``max(position) + 1``, or 0 when none exist).
        """
        self._guard_open()
        base_ns = self._config.base_namespace
        iri = section_iri(doc_id, anchor, base_ns)
        ns = cf_namespace(self._config)
        if self._content_hash_matches(iri, content_hash, ns):
            return iri
        doc_iri = document_iri(doc_id, base_ns)
        resolved_position, resolved_level = self._resolve_section_order(
            iri, doc_iri, ns, position, level
        )
        for q in quads_for_subject(self._store, iri):
            self._staged_removes.append(q)
        for q in build_section_quads(
            doc_id,
            anchor,
            title or anchor,
            narrative_body,
            content_hash,
            doc_id,
            self._config,
            position=resolved_position,
            level=resolved_level,
            contained_entity_ids=sorted(contained_entity_ids or []),
            document_iri_val=doc_iri,
        ):
            self._staged_adds.append(q)
        return iri

    def _resolve_section_order(
        self,
        section_iri_val: str,
        doc_iri: str,
        namespace: str,
        position: int | None,
        level: int | None,
    ) -> tuple[int, int]:
        """Fill in ``position`` / ``level`` so document order survives an update."""
        existing_pos, existing_level = self._section_position_level(section_iri_val, namespace)
        if position is None:
            position = (
                existing_pos
                if existing_pos is not None
                else self._next_section_position(doc_iri, namespace)
            )
        if level is None:
            level = existing_level if existing_level is not None else 2
        return position, level

    def _section_position_level(self, iri: str, namespace: str) -> tuple[int | None, int | None]:
        """Read back a Section's stored ``cf:position`` / ``cf:section_level``."""
        sparql = (
            f"PREFIX cf: <{namespace}> "
            f"SELECT ?pos ?level WHERE {{ <{assert_safe_iri(iri)}> "
            "cf:position ?pos . OPTIONAL { <"
            f"{assert_safe_iri(iri)}> cf:section_level ?level }} }}"
        )
        for row in select_rows(self._store, sparql):
            pos = _strv(_row_lookup(row, "pos"))
            level = _strv(_row_lookup(row, "level"))
            return (
                int(pos) if pos is not None else None,
                int(level) if level is not None else None,
            )
        return None, None

    def _next_section_position(self, doc_iri: str, namespace: str) -> int:
        """Return ``max(cf:position) + 1`` for the document, or 0 when empty."""
        sparql = (
            f"PREFIX cf: <{namespace}> "
            "SELECT (MAX(?pos) AS ?m) WHERE { "
            f"?s a cf:Section ; cf:part_of_document <{assert_safe_iri(doc_iri)}> ; "
            "cf:position ?pos }"
        )
        for row in select_rows(self._store, sparql):
            m = _strv(_row_lookup(row, "m"))
            if m is not None:
                return int(m) + 1
        return 0

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
        removed: list[Any] = []
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
