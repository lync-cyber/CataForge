"""Write entity + relation triples to the KG store idempotently.

Idempotency hinges on the content hash: every entity carries a
`cf:content_hash` triple, and the writer skips an entity whose stored
hash already matches the freshly computed one. Re-running on unchanged
source therefore inserts zero new triples.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cataforge.domain.kg._ask import ask
from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._quads import (
    attribute_subject_quads,
    build_document_quads,
    build_entity_quads,
    build_relation_quad,
    build_section_quads,
    content_hash_matches,
    entity_home_sync_quads,
    stored_entity_iri,
)
from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _term_value,
    assert_safe_iri,
    cf_namespace,
    escape_sparql_literal,
    select_rows,
)
from cataforge.domain.kg.document_guard import ensure_document_replaceable
from cataforge.domain.kg.ingest.entity_extract import ExtractedEntity
from cataforge.domain.kg.ingest.iri import (
    SUBORDINATE_CLASSES,
    document_iri,
    entity_iri,
    resolve_entity_iri,
    section_iri,
)
from cataforge.domain.kg.ingest.relation_extract import ExtractedRelation
from cataforge.domain.kg.ingest.structure_extract import (
    ExtractedDocument,
    ExtractedSection,
)

if TYPE_CHECKING:
    import pyoxigraph as ox


@dataclass
class WriteStats:
    entities_written: int = 0
    entities_skipped: int = 0
    relations_written: int = 0
    relations_skipped: int = 0
    written_iris: list[str] = field(default_factory=list)
    written_relation_quads: list[Any] = field(default_factory=list)
    # (removed, added) quad pairs applied by the hash-skip home sync, so a
    # batch rollback can invert them (they bypass the written_iris ledger).
    home_synced: list[tuple[list[Any], list[Any]]] = field(default_factory=list)


@dataclass
class StructureWriteStats:
    documents_written: int = 0
    documents_skipped: int = 0
    sections_written: int = 0
    sections_skipped: int = 0
    written_iris: list[str] = field(default_factory=list)


_TITLE_LEADING_SEPARATORS = ":：-—– \t"
_BULLET_MARKER_RE = re.compile(r"^[-*+]\s+")


def _strip_entity_id(text: str, entity_id: str) -> str:
    candidate = text.replace(entity_id, "", 1).strip()
    return candidate.lstrip(_TITLE_LEADING_SEPARATORS).strip()


def _title_from_section(section_title: str, entity_id: str) -> str:
    """Section heading often reads `F-001: 用户登录`; strip the id and separator."""
    return _strip_entity_id(section_title, entity_id) or entity_id


def _title_from_line(source_line: str, entity_id: str) -> str:
    """Body line reads `- AC-001: 文本` or a table row; strip markers and the id."""
    text = _BULLET_MARKER_RE.sub("", source_line.strip())
    if text.startswith("|"):
        text = " ".join(cell.strip() for cell in text.strip("|").split("|") if cell.strip())
    return _strip_entity_id(text, entity_id) or entity_id


def _entity_title(entity: ExtractedEntity) -> str:
    if entity.source_line:
        return _title_from_line(entity.source_line, entity.entity_id)
    return _title_from_section(entity.source_section, entity.entity_id)


def _atomic_replace_entity(
    store: ox.Store,
    iri: str,
    new_quads: list[ox.Quad],
    *,
    namespace: str,
) -> None:
    """Replace all quads for `iri` and its attr sub-nodes. Restores prior state on failure."""
    import pyoxigraph as ox  # noqa: PLC0415

    subject = ox.NamedNode(iri)
    prior = list(store.quads_for_pattern(subject, None, None, None))
    prior.extend(attribute_subject_quads(store, iri, namespace))
    added: list[ox.Quad] = []
    try:
        for q in prior:
            store.remove(q)
        for q in new_quads:
            store.add(q)
            added.append(q)
    except Exception:
        for q in reversed(added):
            with contextlib.suppress(Exception):
                store.remove(q)
        for q in prior:
            with contextlib.suppress(Exception):
                store.add(q)
        raise


def write_entities(
    store: ox.Store,
    entities: list[ExtractedEntity],
    project_iri: str,
    config: KGConfig,
) -> WriteStats:
    namespace = cf_namespace(config)
    base_ns = config.base_namespace

    stats = WriteStats()
    for entity in entities:
        iri = resolve_entity_iri(entity.entity_id, entity.class_name, entity.parent_id, base_ns)
        if content_hash_matches(store, iri, entity.content_hash, namespace=namespace):
            removes, adds = entity_home_sync_quads(
                store, iri, entity.source_doc, entity.source_section, namespace=namespace
            )
            for q in removes:
                store.remove(q)
            for q in adds:
                store.add(q)
            if removes or adds:
                stats.home_synced.append((removes, adds))
            stats.entities_skipped += 1
            continue

        new_quads = build_entity_quads(
            entity.entity_id,
            entity.class_name,
            _entity_title(entity),
            entity.source_doc,
            entity.source_section,
            entity.content_hash,
            project_iri,
            config,
            parent_id=entity.parent_id,
            extra_slots=entity.extra_slots or None,
            mtime=entity.mtime,
            attributes=entity.attributes or None,
        )
        _atomic_replace_entity(store, iri, new_quads, namespace=namespace)
        stats.entities_written += 1
        stats.written_iris.append(iri)
    return stats


def revert_home_synced(store: ox.Store, home_synced: list[tuple[list[Any], list[Any]]]) -> None:
    """Invert applied hash-skip home syncs (best-effort).

    Home syncs mutate slots on nodes outside the written-subject ledger, so
    every batch compensation path calls this before its own restore pass.
    """
    for removed, added in reversed(home_synced):
        for q in added:
            with contextlib.suppress(Exception):
                store.remove(q)
        for q in removed:
            with contextlib.suppress(Exception):
                store.add(q)


def _triple_exists(
    store: ox.Store,
    subject: str,
    predicate: str,
    obj: str,
) -> bool:
    assert_safe_iri(subject)
    assert_safe_iri(predicate)
    assert_safe_iri(obj)
    sparql = f"ASK {{ <{subject}> <{predicate}> <{obj}> }}"
    return ask(store, sparql)


def _lookup_node_iri(
    store: ox.Store, config: KGConfig, entity_id: str, source_doc: str
) -> str | None:
    """Return the IRI of the node with this `(entity_id, source_doc)`, or None.

    Resolves a subordinate endpoint to the actual parent-scoped node already
    written to the store, so a relation edge points at the composite IRI rather
    than a non-existent flat one. ``source_doc`` is the logical doc id (its
    bare doc_type, e.g. `prd`); the match is exact. Deterministic first match
    under ambiguity.
    """
    ns = cf_namespace(config)
    eid = escape_sparql_literal(entity_id)
    src = escape_sparql_literal(source_doc)
    exact = (
        f'PREFIX cf: <{ns}> SELECT ?s WHERE {{ ?s cf:entity_id "{eid}" ; '
        f'cf:source_doc "{src}" }} ORDER BY STR(?s) LIMIT 1'
    )
    for row in select_rows(store, exact):
        node = _term_value(_row_lookup(row, "s"))
        if node is not None:
            return str(node)
    return None


def _relation_endpoint_iri(
    store: ox.Store,
    config: KGConfig,
    entity_id: str,
    class_name: str,
    source_doc: str | None,
) -> str:
    """Resolve a relation endpoint's IRI, parent-scoped when subordinate."""
    if class_name not in SUBORDINATE_CLASSES:
        return entity_iri(entity_id, config.base_namespace)
    if source_doc:
        node = _lookup_node_iri(store, config, entity_id, source_doc)
        if node is not None:
            return node
    return entity_iri(entity_id, config.base_namespace)


def write_relations(
    store: ox.Store,
    relations: list[ExtractedRelation],
    config: KGConfig,
) -> WriteStats:
    stats = WriteStats()
    for relation in relations:
        subject_iri_val = _relation_endpoint_iri(
            store, config, relation.subject_entity_id, relation.subject_class, relation.source_doc
        )
        object_iri_val = _relation_endpoint_iri(
            store, config, relation.object_entity_id, relation.object_class, relation.object_doc
        )
        quad = build_relation_quad(
            relation.subject_entity_id,
            relation.predicate_curie,
            relation.object_entity_id,
            config,
            subject_iri=subject_iri_val,
            object_iri=object_iri_val,
        )
        predicate_iri_val = quad.predicate.value

        if _triple_exists(
            store,
            subject_iri_val,
            predicate_iri_val,
            object_iri_val,
        ):
            stats.relations_skipped += 1
            continue

        store.add(quad)
        stats.relations_written += 1
        stats.written_relation_quads.append(quad)
    return stats


def write_structure(
    store: ox.Store,
    documents: list[ExtractedDocument],
    sections: list[ExtractedSection],
    config: KGConfig,
) -> StructureWriteStats:
    """Idempotently write Document + Section structural nodes.

    Skips a node whose stored `cf:content_hash` already matches (same
    rule as `write_entities`), so re-running on unchanged source inserts
    zero new triples.
    """
    namespace = cf_namespace(config)
    base_ns = config.base_namespace
    stats = StructureWriteStats()

    # Gate the whole batch before any write: an approved Document's content
    # is frozen against roundtrip absorbs (ingest / repair).
    for document in documents:
        ensure_document_replaceable(store, config, document.doc_id, document.content_hash)

    for section in sections:
        iri = section_iri(section.doc_id, section.anchor, base_ns)
        if content_hash_matches(store, iri, section.content_hash, namespace=namespace):
            stats.sections_skipped += 1
            continue
        quads = build_section_quads(
            section.doc_id,
            section.anchor,
            section.title,
            section.narrative_body,
            section.content_hash,
            section.source_doc,
            config,
            position=section.position,
            level=section.level,
            contained_entity_ids=section.contained_entity_ids,
            document_iri_val=document_iri(section.doc_id, base_ns),
            resolve_contained_iri=lambda eid: (
                stored_entity_iri(store, eid, namespace=namespace, base_ns=base_ns)
                or entity_iri(eid, base_ns)
            ),
        )
        _atomic_replace_entity(store, iri, quads, namespace=namespace)
        stats.sections_written += 1
        stats.written_iris.append(iri)

    for document in documents:
        iri = document_iri(document.doc_id, base_ns)
        if content_hash_matches(store, iri, document.content_hash, namespace=namespace):
            stats.documents_skipped += 1
            continue
        quads = build_document_quads(
            document.doc_id,
            document.doc_type,
            document.title,
            document.source_doc,
            document.content_hash,
            config,
            section_anchors=document.section_anchors,
            version=document.version,
            status=document.status,
            frontmatter_raw=document.frontmatter_raw,
            preamble_body=document.preamble_body,
            source_path=document.source_path,
        )
        _atomic_replace_entity(store, iri, quads, namespace=namespace)
        stats.documents_written += 1
        stats.written_iris.append(iri)

    _cleanup_stale_structure(store, documents, sections, config)
    return stats


def _remove_subject(store: ox.Store, iri: str, namespace: str) -> None:
    import pyoxigraph as ox  # noqa: PLC0415

    subject = ox.NamedNode(iri)
    doomed = list(store.quads_for_pattern(subject, None, None, None))
    doomed.extend(attribute_subject_quads(store, iri, namespace))
    for q in doomed:
        with contextlib.suppress(Exception):
            store.remove(q)


def _sections_of_document(store: ox.Store, namespace: str, doc_iri: str) -> set[str]:
    safe = assert_safe_iri(doc_iri)
    sparql = (
        f"PREFIX cf: <{namespace}> "
        f"SELECT ?s WHERE {{ ?s a cf:Section ; cf:part_of_document <{safe}> }}"
    )
    out: set[str] = set()
    for row in select_rows(store, sparql):
        val = _term_value(_row_lookup(row, "s"))
        if val:
            out.add(val)
    return out


def stale_section_iris(
    store: ox.Store, namespace: str, doc_iri: str, live_iris: set[str]
) -> set[str]:
    """Section IRIs attached to ``doc_iri`` that ``live_iris`` no longer accounts for.

    The single definition of "stale structure" — both the ingest cleanup and
    the authoring whole-document replace subtract against it.
    """
    return _sections_of_document(store, namespace, doc_iri) - live_iris


def _documents_with_source_path(store: ox.Store, namespace: str, source_path: str) -> set[str]:
    literal = escape_sparql_literal(source_path)
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT ?d WHERE { ?d a cf:Document ; cf:source_path ?p . "
        f'FILTER(STR(?p) = "{literal}") }}'
    )
    out: set[str] = set()
    for row in select_rows(store, sparql):
        val = _term_value(_row_lookup(row, "d"))
        if val:
            out.add(val)
    return out


def _cleanup_stale_structure(
    store: ox.Store,
    documents: list[ExtractedDocument],
    sections: list[ExtractedSection],
    config: KGConfig,
) -> None:
    """Drop structural nodes the fresh extraction no longer accounts for.

    Upsert-by-IRI alone accretes forever: a chapter folded away on disk keeps
    its Section node (and regrows in every render), and a frontmatter doc_id
    rename keeps the old Document node as a ghost twin of the same physical
    file. Scoped to the documents in this migration batch — documents outside
    the ingest scope are untouched.
    """
    namespace = cf_namespace(config)
    base_ns = config.base_namespace
    live_sections: dict[str, set[str]] = {}
    for section in sections:
        live_sections.setdefault(document_iri(section.doc_id, base_ns), set()).add(
            section_iri(section.doc_id, section.anchor, base_ns)
        )
    for document in documents:
        doc_iri = document_iri(document.doc_id, base_ns)
        for stale in stale_section_iris(
            store, namespace, doc_iri, live_sections.get(doc_iri, set())
        ):
            _remove_subject(store, stale, namespace)
        if not document.source_path:
            continue
        for ghost in _documents_with_source_path(store, namespace, document.source_path):
            if ghost == doc_iri:
                continue
            for section_node in _sections_of_document(store, namespace, ghost):
                _remove_subject(store, section_node, namespace)
            _remove_subject(store, ghost, namespace)


def write_project(
    store: ox.Store,
    project_id: str,
    title: str,
    process_model: str,
    config: KGConfig,
) -> str:
    """Idempotently materialize the Project node; return its IRI."""
    import pyoxigraph as ox  # noqa: PLC0415

    from cataforge.domain.kg._quads import XSD_STRING_IRI, _slot_iri
    from cataforge.domain.kg.ingest.iri import class_iri

    namespace = cf_namespace(config)
    base_ns = config.base_namespace
    project_iri_val = entity_iri(project_id, base_ns)
    rdf_type = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
    string_dt = ox.NamedNode(XSD_STRING_IRI)

    sparql = f"ASK {{ <{project_iri_val}> a <{class_iri('Project', namespace)}> }}"
    if ask(store, sparql):
        return project_iri_val

    subject = ox.NamedNode(project_iri_val)
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
    return project_iri_val
