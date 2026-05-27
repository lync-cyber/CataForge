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
from typing import TYPE_CHECKING

from cataforge.kg._ask import ask
from cataforge.kg._config import KGConfig
from cataforge.kg._quads import (
    build_entity_quads,
    build_relation_quad,
    quads_for_subject,
)
from cataforge.kg.ingest.entity_extract import ExtractedEntity
from cataforge.kg.ingest.iri import entity_iri
from cataforge.kg.ingest.relation_extract import ExtractedRelation

if TYPE_CHECKING:
    import pyoxigraph as ox


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


def _title_from_section(section_title: str, entity_id: str) -> str:
    """Section heading often reads `F-001 用户登录`; strip the entity_id."""
    candidate = section_title.replace(entity_id, "", 1).strip()
    return candidate or entity_id


def write_entities(
    store: ox.Store,
    entities: list[ExtractedEntity],
    project_iri: str,
    config: KGConfig,
) -> WriteStats:
    namespace = config.ontology_namespace.rstrip("/") + "/"
    base_ns = config.base_namespace

    stats = WriteStats()
    for entity in entities:
        iri = entity_iri(entity.entity_id, base_ns)
        if _content_hash_matches(
            store, iri, entity.content_hash, namespace=namespace
        ):
            stats.entities_skipped += 1
            continue

        for q in quads_for_subject(store, iri):
            store.remove(q)

        for q in build_entity_quads(
            entity.entity_id,
            entity.class_name,
            _title_from_section(entity.source_section, entity.entity_id),
            entity.source_doc,
            entity.source_section,
            entity.content_hash,
            project_iri,
            config,
            mtime=entity.mtime,
        ):
            store.add(q)

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
    namespace = config.ontology_namespace.rstrip("/") + "/"
    base_ns = config.base_namespace

    stats = WriteStats()
    for relation in relations:
        subject_iri_val = entity_iri(relation.subject_entity_id, base_ns)
        object_iri_val = entity_iri(relation.object_entity_id, base_ns)
        quad = build_relation_quad(
            relation.subject_entity_id,
            relation.predicate_curie,
            relation.object_entity_id,
            config,
        )
        predicate_iri_val = quad.predicate.value

        if _triple_exists(
            store,
            subject_iri_val,
            predicate_iri_val,
            object_iri_val,
            namespace=namespace,
        ):
            stats.relations_skipped += 1
            continue

        store.add(quad)
        stats.relations_written += 1
    return stats


def write_project(
    store: ox.Store,
    project_id: str,
    title: str,
    process_model: str,
    config: KGConfig,
) -> str:
    """Idempotently materialize the Project node; return its IRI."""
    import pyoxigraph as ox  # noqa: PLC0415

    from cataforge.kg._quads import XSD_STRING_IRI, _slot_iri
    from cataforge.kg.ingest.iri import class_iri

    namespace = config.ontology_namespace.rstrip("/") + "/"
    base_ns = config.base_namespace
    project_iri_val = entity_iri(project_id, base_ns)
    rdf_type = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    string_dt = ox.NamedNode(XSD_STRING_IRI)

    sparql = (
        f"ASK {{ <{project_iri_val}> a <{class_iri('Project', namespace)}> }}"
    )
    if ask(store, sparql):
        return project_iri_val

    subject = ox.NamedNode(project_iri_val)
    store.add(
        ox.Quad(
            subject, rdf_type, ox.NamedNode(class_iri("Project", namespace))
        )
    )
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
    return project_iri_val
