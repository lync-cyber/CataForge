"""Quad construction helpers shared by ingest/writer.py and TransactionContext."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._sparql_utils import cf_namespace
from cataforge.domain.kg.ingest.iri import (
    class_iri,
    document_iri,
    entity_iri,
    section_iri,
)

if TYPE_CHECKING:
    import pyoxigraph as ox

_PREFIX_LEN_PADDING = 6

RDF_TYPE_IRI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
XSD_STRING_IRI = "http://www.w3.org/2001/XMLSchema#string"
XSD_DATETIME_IRI = "http://www.w3.org/2001/XMLSchema#dateTime"


def _slot_iri(slot_curie: str, namespace: str) -> str:
    if ":" not in slot_curie:
        return f"{namespace.rstrip('/')}/{slot_curie}"
    head, tail = slot_curie.split(":", 1)
    if head == "cf":
        return f"{namespace.rstrip('/')}/{tail}"
    return slot_curie


def _sort_key(entity_id: str) -> str:
    parts = (entity_id or "").split("-", 1)
    if len(parts) < 2:
        return entity_id or ""
    prefix, numeric = parts
    try:
        return f"{prefix}:{int(numeric):0{_PREFIX_LEN_PADDING}d}"
    except ValueError:
        return entity_id


def build_entity_quads(
    entity_id: str,
    class_name: str,
    title: str,
    source_doc: str,
    source_section: str,
    content_hash: str,
    project_iri: str,
    config: KGConfig,
    *,
    extra_slots: dict[str, str] | None = None,
    mtime: float | None = None,
) -> list[ox.Quad]:
    """Return the complete set of quads describing one entity."""
    import pyoxigraph as ox  # noqa: PLC0415

    namespace = cf_namespace(config)
    base_ns = config.base_namespace
    iri = entity_iri(entity_id, base_ns)
    subject = ox.NamedNode(iri)
    rdf_type = ox.NamedNode(RDF_TYPE_IRI)
    string_dt = ox.NamedNode(XSD_STRING_IRI)
    project_node = ox.NamedNode(project_iri)

    quads: list[ox.Quad] = [
        ox.Quad(subject, rdf_type, ox.NamedNode(class_iri(class_name, namespace))),
    ]

    for slot, value in (
        ("entity_id", entity_id),
        ("sort_key", _sort_key(entity_id)),
        ("title", title),
        ("source_doc", source_doc),
        ("source_section", source_section),
        ("content_hash", content_hash),
    ):
        quads.append(
            ox.Quad(
                subject,
                ox.NamedNode(_slot_iri(f"cf:{slot}", namespace)),
                ox.Literal(value, datatype=string_dt),
            )
        )

    ts = mtime if mtime is not None else datetime.now(timezone.utc).timestamp()
    updated_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    quads.append(
        ox.Quad(
            subject,
            ox.NamedNode(_slot_iri("cf:updated_at", namespace)),
            ox.Literal(updated_at, datatype=ox.NamedNode(XSD_DATETIME_IRI)),
        )
    )

    quads.append(
        ox.Quad(
            subject,
            ox.NamedNode(_slot_iri("cf:belongs_to_project", namespace)),
            project_node,
        )
    )

    if extra_slots:
        for slot_curie, value in extra_slots.items():
            values = value if isinstance(value, list) else [value]
            for v in values:
                quads.append(
                    ox.Quad(
                        subject,
                        ox.NamedNode(_slot_iri(slot_curie, namespace)),
                        ox.Literal(v, datatype=string_dt),
                    )
                )

    return quads


def build_section_quads(
    doc_id: str,
    anchor: str,
    title: str,
    narrative_body: str,
    content_hash: str,
    source_doc: str,
    config: KGConfig,
    *,
    contained_entity_ids: list[str] | None = None,
    document_iri_val: str | None = None,
) -> list[ox.Quad]:
    """Return the quads describing one Section structural node.

    Identity is the section IRI (no `cf:entity_id` — Sections are
    structural, identified by the `id` IRI like Project/Document).
    """
    import pyoxigraph as ox  # noqa: PLC0415

    namespace = cf_namespace(config)
    base_ns = config.base_namespace
    subject = ox.NamedNode(section_iri(doc_id, anchor, base_ns))
    string_dt = ox.NamedNode(XSD_STRING_IRI)

    quads: list[ox.Quad] = [
        ox.Quad(subject, ox.NamedNode(RDF_TYPE_IRI), ox.NamedNode(class_iri("Section", namespace))),
    ]
    for slot, value in (
        ("title", title),
        ("section_anchor", anchor),
        ("narrative_body", narrative_body),
        ("content_hash", content_hash),
        ("source_doc", source_doc),
        ("sort_key", anchor),
    ):
        quads.append(
            ox.Quad(
                subject,
                ox.NamedNode(_slot_iri(f"cf:{slot}", namespace)),
                ox.Literal(value, datatype=string_dt),
            )
        )
    if document_iri_val:
        quads.append(
            ox.Quad(
                subject,
                ox.NamedNode(_slot_iri("cf:part_of_document", namespace)),
                ox.NamedNode(document_iri_val),
            )
        )
    for eid in contained_entity_ids or []:
        quads.append(
            ox.Quad(
                subject,
                ox.NamedNode(_slot_iri("cf:contains_entity", namespace)),
                ox.NamedNode(entity_iri(eid, base_ns)),
            )
        )
    return quads


def build_document_quads(
    doc_id: str,
    doc_type: str,
    title: str,
    source_doc: str,
    content_hash: str,
    config: KGConfig,
    *,
    section_anchors: list[str] | None = None,
    version: str | None = None,
    status: str | None = None,
) -> list[ox.Quad]:
    """Return the quads describing one Document structural node."""
    import pyoxigraph as ox  # noqa: PLC0415

    namespace = cf_namespace(config)
    base_ns = config.base_namespace
    subject = ox.NamedNode(document_iri(doc_id, base_ns))
    string_dt = ox.NamedNode(XSD_STRING_IRI)

    quads: list[ox.Quad] = [
        ox.Quad(
            subject, ox.NamedNode(RDF_TYPE_IRI), ox.NamedNode(class_iri("Document", namespace))
        ),
    ]
    literal_slots = [
        ("title", title),
        ("doc_type", doc_type),
        ("source_doc", source_doc),
        ("content_hash", content_hash),
    ]
    if version:
        literal_slots.append(("version", version))
    if status:
        literal_slots.append(("status", status))
    for slot, value in literal_slots:
        quads.append(
            ox.Quad(
                subject,
                ox.NamedNode(_slot_iri(f"cf:{slot}", namespace)),
                ox.Literal(value, datatype=string_dt),
            )
        )
    for anchor in section_anchors or []:
        quads.append(
            ox.Quad(
                subject,
                ox.NamedNode(_slot_iri("cf:has_section", namespace)),
                ox.NamedNode(section_iri(doc_id, anchor, base_ns)),
            )
        )
    return quads


def build_relation_quad(
    subject_id: str,
    predicate_curie: str,
    object_id: str,
    config: KGConfig,
) -> ox.Quad:
    """Return a single traceability-edge quad."""
    import pyoxigraph as ox  # noqa: PLC0415

    namespace = cf_namespace(config)
    base_ns = config.base_namespace
    return ox.Quad(
        ox.NamedNode(entity_iri(subject_id, base_ns)),
        ox.NamedNode(_slot_iri(predicate_curie, namespace)),
        ox.NamedNode(entity_iri(object_id, base_ns)),
    )


def quads_for_subject(store: ox.Store, iri: str) -> list[ox.Quad]:
    """Return every quad with `iri` as subject."""
    import pyoxigraph as ox  # noqa: PLC0415

    return list(store.quads_for_pattern(ox.NamedNode(iri), None, None, None))


def quads_targeting(store: ox.Store, iri: str) -> list[ox.Quad]:
    """Return every quad with `iri` as object (incoming edges)."""
    import pyoxigraph as ox  # noqa: PLC0415

    return list(store.quads_for_pattern(None, None, ox.NamedNode(iri), None))


__all__ = [
    "build_document_quads",
    "build_entity_quads",
    "build_relation_quad",
    "build_section_quads",
    "quads_for_subject",
    "quads_targeting",
]
