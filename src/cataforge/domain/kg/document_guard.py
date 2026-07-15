"""Approved-document replace guard shared by every structure-write entry.

An approved Document's content is frozen. The one write allowed through is an
explicit re-author that deliberately keeps the document approved — in that
path the frontmatter status is an API argument the author set. A
file-roundtrip absorb (ingest / repair) merely echoes the exported
frontmatter and carries no such intent, so it is always refused. Status
transitions go through `context write-meta`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cataforge.domain.kg._errors import KGValidationError
from cataforge.domain.kg._quads import content_hash_matches
from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _strv,
    assert_safe_iri,
    cf_namespace,
    select_rows,
)
from cataforge.domain.kg.ingest.iri import document_iri

if TYPE_CHECKING:
    import pyoxigraph as ox

    from cataforge.domain.kg._config import KGConfig


def document_status(store: ox.Store, config: KGConfig, doc_id: str) -> str | None:
    """The stored Document's `cf:status` literal, or None when absent."""
    ns = cf_namespace(config)
    iri = assert_safe_iri(document_iri(doc_id, config.base_namespace))
    sparql = f"PREFIX cf: <{ns}> SELECT ?s WHERE {{ <{iri}> cf:status ?s }} LIMIT 1"
    for row in select_rows(store, sparql):
        return _strv(_row_lookup(row, "s"))
    return None


def ensure_document_replaceable(
    store: ox.Store,
    config: KGConfig,
    doc_id: str,
    content_hash: str,
    *,
    incoming_status: str | None = None,
    explicit_status_intent: bool = False,
) -> None:
    """Raise :class:`KGValidationError` when a write would alter an approved
    Document's content.

    Identical content (hash match) is always allowed — the upsert is a no-op
    upstream. ``explicit_status_intent`` marks the authoring path, whose
    frontmatter status is a deliberate API argument: keeping ``approved``
    passes, anything else is a silent downgrade and is refused. The
    roundtrip-absorb paths (ingest / repair) pass ``False`` and are refused
    outright.
    """
    if document_status(store, config, doc_id) != "approved":
        return
    iri = document_iri(doc_id, config.base_namespace)
    if content_hash_matches(store, iri, content_hash, namespace=cf_namespace(config)):
        return
    if explicit_status_intent:
        if incoming_status == "approved":
            return
        raise KGValidationError(
            f"Document {doc_id!r} is approved — transition its status via "
            "`context write-meta` before re-authoring content; re-authoring would "
            f"silently downgrade it to {incoming_status or 'draft'!r}."
        )
    raise KGValidationError(
        f"Document {doc_id!r} is approved — its content is frozen against ingest. "
        "Transition its status via `context write-meta` (then re-ingest), or revert "
        "the Markdown to the exported content."
    )
