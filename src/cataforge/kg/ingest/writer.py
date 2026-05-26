"""Phase 5 of task-7 §7.2: write entity + relation triples idempotently.

Idempotency hinges on the content hash: every entity carries a
`cf:content_hash` triple, and the writer skips an entity whose stored
hash already matches the freshly computed one. Re-running the codemod
on unchanged source therefore inserts zero new triples.

Every ASK in this module flows through
`cataforge.kg._ask.ask(store, sparql) -> bool` — the chokepoint that
forces `QueryBoolean → bool` (spike-2 §2.2, issue #142). This is the
first production-path consumer of the chokepoint.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from cataforge.kg._ask import ask
from cataforge.kg._config import KGConfig
from cataforge.kg.ingest.entity_extract import ExtractedEntity
from cataforge.kg.ingest.iri import (
    DEFAULT_ONTOLOGY_NS,
    class_iri,
    entity_iri,
)
from cataforge.kg.ingest.relation_extract import ExtractedRelation

if TYPE_CHECKING:
    import pyoxigraph as ox


_PREFIX_LEN_PADDING = 6


def _sort_key(entity_id: str) -> str:
    prefix, numeric = entity_id.split("-", 1)
    return f"{prefix}:{int(numeric):0{_PREFIX_LEN_PADDING}d}"


def _title_from_section(section_title: str, entity_id: str) -> str:
    """Section heading often reads `F-001 用户登录`; strip the entity_id."""
    candidate = section_title.replace(entity_id, "", 1).strip()
    return candidate or entity_id


def _slot_iri(slot_curie: str, namespace: str = DEFAULT_ONTOLOGY_NS) -> str:
    if ":" not in slot_curie:
        return f"{namespace.rstrip('/')}/{slot_curie}"
    head, tail = slot_curie.split(":", 1)
    if head == "cf":
        return f"{namespace.rstrip('/')}/{tail}"
    return slot_curie  # already an absolute IRI (or unknown prefix)


@dataclass
class WriteStats:
    entities_written: int = 0
    entities_skipped: int = 0
    relations_written: int = 0
    relations_skipped: int = 0


def _content_hash_matches(
    store: ox.Store,
    iri: str,
    content_hash: str,
    *,
    namespace: str,
) -> bool:
    """Has this exact (iri, content_hash) pair already been ingested?"""
    sparql = (
        f"PREFIX cf: <{namespace}> "
        f'ASK {{ <{iri}> cf:content_hash "{content_hash}" }}'
    )
    return ask(store, sparql)


def _delete_existing_entity(store: ox.Store, iri: str) -> None:
    """Remove every triple with subject `iri` before re-writing.

    Used when the content_hash changed: we want a clean slot set rather
    than a graph that accumulates stale literals from earlier ingests.
    """
    import pyoxigraph as ox  # noqa: PLC0415

    subject = ox.NamedNode(iri)
    for quad in list(store.quads_for_pattern(subject, None, None, None)):
        store.remove(quad)


def write_entities(
    store: ox.Store,
    entities: list[ExtractedEntity],
    project_iri: str,
    config: KGConfig,
) -> WriteStats:
    import pyoxigraph as ox  # noqa: PLC0415

    namespace = config.ontology_namespace.rstrip("/") + "/"
    base_ns = config.base_namespace
    rdf_type = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    project_node = ox.NamedNode(project_iri)
    string_dt = ox.NamedNode("http://www.w3.org/2001/XMLSchema#string")

    stats = WriteStats()
    for entity in entities:
        iri = entity_iri(entity.entity_id, base_ns)
        if _content_hash_matches(
            store, iri, entity.content_hash, namespace=namespace
        ):
            stats.entities_skipped += 1
            continue

        _delete_existing_entity(store, iri)

        subject = ox.NamedNode(iri)
        cls_node = ox.NamedNode(class_iri(entity.class_name, namespace))
        store.add(ox.Quad(subject, rdf_type, cls_node))

        for slot, value in (
            ("entity_id", entity.entity_id),
            ("sort_key", _sort_key(entity.entity_id)),
            ("title", _title_from_section(entity.source_section, entity.entity_id)),
            ("source_doc", entity.source_doc),
            ("source_section", entity.source_section),
            ("content_hash", entity.content_hash),
        ):
            store.add(
                ox.Quad(
                    subject,
                    ox.NamedNode(_slot_iri(f"cf:{slot}", namespace)),
                    ox.Literal(value, datatype=string_dt),
                )
            )

        updated_at = datetime.fromtimestamp(entity.mtime, tz=timezone.utc).isoformat()
        store.add(
            ox.Quad(
                subject,
                ox.NamedNode(_slot_iri("cf:updated_at", namespace)),
                ox.Literal(
                    updated_at,
                    datatype=ox.NamedNode(
                        "http://www.w3.org/2001/XMLSchema#dateTime"
                    ),
                ),
            )
        )

        store.add(
            ox.Quad(
                subject,
                ox.NamedNode(_slot_iri("cf:belongs_to_project", namespace)),
                project_node,
            )
        )
        stats.entities_written += 1
    return stats


def _triple_exists(
    store: ox.Store, subject: str, predicate: str, obj: str, *, namespace: str
) -> bool:
    sparql = f"ASK {{ <{subject}> <{predicate}> <{obj}> }}"
    return ask(store, sparql)


def write_relations(
    store: ox.Store,
    relations: list[ExtractedRelation],
    config: KGConfig,
) -> WriteStats:
    import pyoxigraph as ox  # noqa: PLC0415

    namespace = config.ontology_namespace.rstrip("/") + "/"
    base_ns = config.base_namespace

    stats = WriteStats()
    for relation in relations:
        subject_iri = entity_iri(relation.subject_entity_id, base_ns)
        object_iri = entity_iri(relation.object_entity_id, base_ns)
        predicate_iri = _slot_iri(relation.predicate_curie, namespace)

        if _triple_exists(
            store, subject_iri, predicate_iri, object_iri, namespace=namespace
        ):
            stats.relations_skipped += 1
            continue

        store.add(
            ox.Quad(
                ox.NamedNode(subject_iri),
                ox.NamedNode(predicate_iri),
                ox.NamedNode(object_iri),
            )
        )
        stats.relations_written += 1
    return stats


def write_project(
    store: ox.Store,
    project_id: str,
    title: str,
    process_model: str,
    config: KGConfig,
) -> str:
    """Idempotently materialize the Project node; return its IRI.

    Skipped if `<project_iri> rdf:type cf:Project` already exists.
    """
    import pyoxigraph as ox  # noqa: PLC0415

    namespace = config.ontology_namespace.rstrip("/") + "/"
    base_ns = config.base_namespace
    project_iri = entity_iri(project_id, base_ns)
    rdf_type = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    string_dt = ox.NamedNode("http://www.w3.org/2001/XMLSchema#string")

    sparql = (
        f"ASK {{ <{project_iri}> a <{class_iri('Project', namespace)}> }}"
    )
    if ask(store, sparql):
        return project_iri

    subject = ox.NamedNode(project_iri)
    store.add(ox.Quad(subject, rdf_type, ox.NamedNode(class_iri("Project", namespace))))
    store.add(
        ox.Quad(
            subject,
            ox.NamedNode(_slot_iri("cf:title", namespace)),
            ox.Literal(title, datatype=string_dt),
        )
    )
    store.add(
        ox.Quad(
            subject,
            ox.NamedNode(_slot_iri("cf:process_model", namespace)),
            ox.Literal(process_model, datatype=string_dt),
        )
    )
    return project_iri
