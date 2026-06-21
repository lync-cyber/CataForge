"""Mode-routed authoring — the write side of the context lifecycle.

Each lifecycle operation routes on the project's ``context.mode`` via
:class:`~cataforge.domain.kg.authority.ModePolicy`. Under ``graph`` the
knowledge graph is the source of truth: authoring writes go to the graph under
write-time schema validation, then Markdown is *exported* as a human-review
view (``finalize``); human edits to the exported Markdown are reflected back
with ``ingest``, and ``reconcile`` guards the two against drift. Under
``hybrid`` Markdown is canonical and the graph is a derived index: ``finalize``
/ ``ingest`` sync md → KG and rebuild the docs index, and direct graph
authoring is rejected (edit Markdown, then ingest). Under ``markdown`` there is
no graph at all: ``finalize`` / ``ingest`` rebuild the docs index, ``reconcile``
validates its integrity, and graph authoring is rejected.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cataforge.core.errors import CataforgeError
from cataforge.domain.kg import KnowledgeGraph
from cataforge.domain.kg._content_hash import entity_content_hash
from cataforge.domain.kg._dispatch import (
    definition_authority,
    kg_config_for,
    kg_enabled,
)
from cataforge.domain.kg._errors import KGEntityNotFoundError, KGValidationError
from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _strv,
    assert_safe_iri,
    cf_namespace,
    escape_sparql_literal,
    select_rows,
)
from cataforge.domain.kg.authority import ModePolicy
from cataforge.domain.kg.export import entity_doc_type
from cataforge.domain.kg.export.document_pipeline import compile_documents
from cataforge.domain.kg.export.types import CompileResult
from cataforge.domain.kg.ingest import DEFAULT_DOC_TYPES, parse_doc_text, run_migration
from cataforge.domain.kg.ingest.entity_extract import extract_entities
from cataforge.domain.kg.ingest.frontmatter import _PARSE_ERROR_KEY
from cataforge.domain.kg.ingest.iri import document_iri, id_prefix_to_type, section_iri
from cataforge.domain.kg.ingest.migrate import _read_project_metadata
from cataforge.domain.kg.ingest.relation_extract import extract_relations
from cataforge.domain.kg.ingest.structure_extract import extract_structure
from cataforge.domain.kg.ingest.writer import _entity_title, write_project
from cataforge.domain.kg.reconcile import reconcile as _reconcile
from cataforge.domain.kg.validate import validate

if TYPE_CHECKING:
    import pyoxigraph as ox

    from cataforge.domain.kg.ingest.entity_extract import ExtractedEntity
    from cataforge.domain.kg.ingest.migrate import MigrationStats
    from cataforge.domain.kg.ingest.relation_extract import ExtractedRelation
    from cataforge.domain.kg.ingest.structure_extract import ExtractedSection
    from cataforge.domain.kg.reconcile import ReconcileReport
    from cataforge.domain.kg.transaction import TransactionContext
    from cataforge.domain.kg.validate import ValidationViolation


class ContextModeError(CataforgeError):
    """Raised when an operation needs a backend the project's
    ``context.mode`` does not enable."""


@dataclass(frozen=True)
class DocIndexResult:
    """Outcome of a lifecycle write routed to the docs-index backend."""

    indexed_count: int
    index_path: Path


@dataclass(frozen=True)
class TransactResult:
    """Outcome of a multi-op ``transact`` commit."""

    entities_written: int
    relations_written: int
    sections_written: int


@dataclass(frozen=True)
class AuthorDocumentResult:
    """Outcome of an ``author_document`` whole-file write into the graph."""

    doc_id: str
    document_iri: str
    sections_written: int
    entities_written: int
    relations_written: int


@dataclass(frozen=True)
class UpdateDocumentMetaResult:
    """Outcome of an ``update_document_meta`` frontmatter status/version patch."""

    doc_id: str
    document_iri: str
    status: str | None
    version: str | None


@dataclass(frozen=True)
class DocValidationReport:
    """Reconcile outcome when the docs index is the backend under guard.

    Mirrors the drift-guard surface of ``ReconcileReport`` (``ok`` /
    ``overall_divergence_count``) so callers handle both uniformly.
    """

    issue_counts: dict[str, int]

    @property
    def overall_divergence_count(self) -> int:
        return sum(self.issue_counts.values())

    @property
    def ok(self) -> bool:
        return self.overall_divergence_count == 0


_DOC_VALIDATION_GATES = ("orphans", "stale", "xref_errors", "alias_conflicts", "invalid_ids")


def _require_graph_mode(project_root: str, capability: str) -> None:
    """Gate a direct-graph-authoring op to ``context.mode = graph``.

    The graph is canonical only under ``graph`` mode, so a direct write is
    meaningful only there. ``hybrid`` keeps Markdown canonical (a direct graph
    write would be clobbered by the next md → KG sync), and ``markdown`` has no
    graph at all — both reject with the path back to the supported flow.
    """
    policy = ModePolicy.for_project(project_root)
    if policy.graph_authoring_allowed:
        return
    if policy.graph_enabled:  # hybrid
        raise ContextModeError(
            f"{capability} authors directly into the knowledge graph, which is "
            'canonical only under context.mode = "graph". This project is '
            '"hybrid" (Markdown is canonical) — edit the documents under docs/ '
            "and run `cataforge context ingest`, or switch context.mode to graph."
        )
    raise ContextModeError(
        f"{capability} authors into the knowledge graph, but this project is "
        'context.mode = "markdown" (no graph backend) — edit the documents '
        "under docs/ directly instead."
    )


def _rebuild_doc_index(project_root: str) -> DocIndexResult:
    from cataforge.domain.docs.indexer import build_full_index, write_index

    index = build_full_index(project_root)
    out_path = write_index(index, project_root)
    return DocIndexResult(indexed_count=len(index.get("documents", {})), index_path=Path(out_path))


def _validate_doc_index(project_root: str) -> DocValidationReport:
    from cataforge.domain.docs.indexer import INDEX_FILENAME, validate_docs

    index_path = Path(project_root) / "docs" / INDEX_FILENAME
    if not index_path.is_file():
        err = CataforgeError(
            f"docs/{INDEX_FILENAME} not found at {project_root} — nothing to reconcile.\n"
            "Hint: run `cataforge docs index` first."
        )
        err.exit_code = 2
        raise err
    result = validate_docs(str(project_root))
    return DocValidationReport(
        issue_counts={gate: len(result.get(gate, [])) for gate in _DOC_VALIDATION_GATES}
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_HEADING_RE = re.compile(r"^(#{2,6})\s+(.*\S)\s*$")


def _existing_source_doc(store: ox.Store, cfg: Any, entity_id: str) -> str | None:
    """Return an entity's stored ``cf:source_doc``, or ``None`` when it is new.

    Re-authoring an existing entity must keep its document membership; the
    ``entity_doc_type`` default would relocate it to the bare doc_type and
    orphan it (a Module from ``arch-temp`` would collapse onto ``arch``).
    """
    ns = cf_namespace(cfg)
    eid = escape_sparql_literal(entity_id)
    sparql = (
        f"PREFIX cf: <{ns}> "
        f'SELECT ?d WHERE {{ ?s cf:entity_id "{eid}" ; cf:source_doc ?d }} LIMIT 1'
    )
    for row in select_rows(store, sparql):
        return _strv(_row_lookup(row, "d"))
    return None


def _existing_section_level(store: ox.Store, cfg: Any, doc_id: str, anchor: str) -> int | None:
    """Read back a Section's stored ``cf:section_level``, or ``None``."""
    ns = cf_namespace(cfg)
    iri = section_iri(doc_id, anchor, cfg.base_namespace)
    sparql = (
        f"PREFIX cf: <{ns}> "
        f"SELECT ?level WHERE {{ <{assert_safe_iri(iri)}> cf:section_level ?level }}"
    )
    for row in select_rows(store, sparql):
        level = _strv(_row_lookup(row, "level"))
        if level is not None:
            return int(level)
    return None


def _normalize_narrative(
    narrative: str, anchor: str, *, existing_level: int | None
) -> tuple[str, int]:
    """Return ``(narrative_body, level)`` with a leading heading guaranteed.

    The export pipeline concatenates each Section's ``narrative_body``
    verbatim, so the body must carry its own heading line. If the first
    non-blank line is a level-2..6 heading, its text must equal ``anchor``
    (a mismatch produces ghost/missing sections on export) and its depth
    sets the level. Otherwise a ``{'#' * level} {anchor}`` line is prepended,
    with ``level`` taken from the existing section (default 2).
    """
    lines = narrative.split("\n")
    first_idx = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if first_idx is not None:
        m = _HEADING_RE.match(lines[first_idx])
        if m is not None:
            heading_text = m.group(2).strip()
            if heading_text != anchor:
                raise KGValidationError(
                    f"section heading {heading_text!r} does not match anchor {anchor!r}; "
                    "a heading/anchor mismatch produces a ghost or missing section on export — "
                    "make the first heading line read exactly the anchor text."
                )
            return narrative, len(m.group(1))
    level = existing_level if existing_level is not None else 2
    return f"{'#' * level} {anchor}\n{narrative}", level


def _check_entity_class(entity_id: str, class_name: str) -> None:
    """Deterministic schema gate: the entity_id prefix must map to class_name.

    Catches the common authoring errors (wrong prefix for the class, or an
    id with no schema-known prefix) without relying on an optional SHACL
    engine being installed.
    """
    expected = id_prefix_to_type(entity_id)
    if expected is None:
        raise KGValidationError(f"entity_id {entity_id!r} has no schema-known prefix")
    if expected != class_name:
        raise KGValidationError(f"entity_id {entity_id!r} maps to {expected}, not {class_name!r}")


def _scoped_delete_id(entity_id: str, parent_id: str | None) -> str:
    """The delete-target id for an entity, parent-scoped when subordinate."""
    return f"{parent_id}/{entity_id}" if parent_id else entity_id


def _stage_entity(
    txn: TransactionContext,
    *,
    project_iri: str,
    entity_id: str,
    class_name: str,
    title: str,
    slots: dict[str, str] | None,
    parent_id: str | None,
    narrative: str | None,
    relations: list[tuple[str, str]] | None,
    source_section: str,
    source_doc: str | None = None,
) -> str:
    """Stage one entity (with slots / narrative / outgoing edges) into ``txn``.

    Returns the entity IRI. The entity_id↔class gate runs first. ``source_doc``
    overrides the ``entity_doc_type`` default so a re-authored entity keeps its
    existing document membership instead of collapsing onto the bare doc_type.
    """
    _check_entity_class(entity_id, class_name)
    merged: dict[str, str] = dict(slots or {})
    if narrative is not None:
        merged["narrative_body"] = narrative
    extra = {f"cf:{k}": v for k, v in merged.items()} or None
    content_hash = entity_content_hash(title, slots)
    iri = txn.add_entity(
        entity_id,
        class_name,
        title,
        source_doc or entity_doc_type(class_name),
        source_section,
        content_hash,
        project_iri,
        parent_id=parent_id,
        extra_slots=extra,
    )
    for predicate, object_id in relations or []:
        txn.add_relation(entity_id, predicate, object_id, subject_iri=iri)
    return iri


def _offends(
    report_violations: list[ValidationViolation], ids: set[str]
) -> list[ValidationViolation]:
    return [v for v in report_violations if v.entity_id in ids]


def author_entity(
    project_root: str,
    *,
    entity_id: str,
    class_name: str,
    title: str,
    slots: dict[str, str] | None = None,
    source_section: str = "",
    project_id: str | None = None,
    parent_id: str | None = None,
    relations: list[tuple[str, str]] | None = None,
    narrative: str | None = None,
) -> str:
    """Authorize-and-write one entity to the graph; return its IRI.

    Requires ``context.mode = graph``. A subordinate ``parent_id`` yields a
    parent-scoped IRI plus a ``cf:part_of`` edge; ``relations`` add outgoing
    traceability edges; ``narrative`` is stored as the ``cf:narrative_body``
    slot — all in one transaction. The entity_id↔class gate runs up front, and
    a post-commit ``validate`` pass compensates (deletes the just-written
    entity and its edges) and raises if it introduced any violation.
    """
    _require_graph_mode(project_root, "entity authoring (`context write`)")
    cfg = kg_config_for(project_root)
    meta = _read_project_metadata(Path(project_root))
    pid = project_id or meta["project_id"]

    with KnowledgeGraph.connect(cfg) as kg:
        project_iri = write_project(kg.store, pid, meta["title"], meta["process_model"], cfg)
        existing_source_doc = _existing_source_doc(kg.store, cfg, entity_id)
        with kg.transaction() as txn:
            iri = _stage_entity(
                txn,
                project_iri=project_iri,
                entity_id=entity_id,
                class_name=class_name,
                title=title,
                slots=slots,
                parent_id=parent_id,
                narrative=narrative,
                relations=relations,
                source_section=source_section,
                source_doc=existing_source_doc,
            )
        report = validate(kg.store, cfg)
        offending = _offends(report.violations, {entity_id, iri})
        if offending:
            with kg.transaction() as undo:
                undo.delete_entity(_scoped_delete_id(entity_id, parent_id), cascade=True)
            detail = "; ".join(f"{v.shape}: {v.message}" for v in offending)
            raise KGValidationError(f"authored entity {entity_id} failed validation: {detail}")
    return iri


def write_narrative(
    project_root: str,
    *,
    doc_id: str,
    anchor: str,
    narrative: str,
    contained_entity_ids: list[str] | None = None,
) -> None:
    """Author a Section's prose (``narrative_body``) directly into the graph.

    Requires ``context.mode = graph``. The body is normalized to carry its
    heading line (see :func:`_normalize_narrative`) so the export pipeline
    reconstructs the section verbatim, and stored through the transaction
    face so an updated section keeps its ``cf:position`` document order.
    """
    _require_graph_mode(project_root, "narrative authoring (`context write-narrative`)")
    cfg = kg_config_for(project_root)
    with KnowledgeGraph.connect(cfg) as kg:
        level = _existing_section_level(kg.store, cfg, doc_id, anchor)
        body, resolved_level = _normalize_narrative(narrative, anchor, existing_level=level)
        with kg.transaction() as txn:
            txn.add_section(
                doc_id,
                anchor,
                body,
                _sha256(body),
                level=resolved_level,
                title=anchor,
                contained_entity_ids=contained_entity_ids,
            )


_TRANSACT_OPS = ("add_entity", "add_relation", "write_narrative")


def _require_keys(op: dict[str, Any], keys: tuple[str, ...], op_name: str) -> None:
    missing = [k for k in keys if k not in op]
    if missing:
        raise KGValidationError(f"{op_name} op missing required key(s): {', '.join(missing)}")


def transact(project_root: str, spec: dict[str, Any]) -> TransactResult:
    """Apply a batch of authoring operations in a single atomic transaction.

    ``spec`` is ``{"operations": [op, ...]}`` where each op carries an ``op``
    discriminator: ``add_entity`` (entity_id / class / title, optional parent /
    slots / narrative / relations), ``add_relation`` (subject / predicate /
    object), or ``write_narrative`` (doc_id / anchor / narrative). Requires
    ``context.mode = graph``. All ops stage into one ``TransactionContext`` and
    commit together; a post-commit ``validate`` over the written entities
    compensates the whole batch on any violation — zero graph residue.
    """
    _require_graph_mode(project_root, "batch authoring (`context transact`)")
    operations = spec.get("operations")
    if not isinstance(operations, list):
        raise KGValidationError("transact spec must carry an 'operations' list")

    cfg = kg_config_for(project_root)
    meta = _read_project_metadata(Path(project_root))
    written_ids: set[str] = set()
    delete_ids: list[str] = []
    counts = {"entities": 0, "relations": 0, "sections": 0}

    with KnowledgeGraph.connect(cfg) as kg:
        project_iri = write_project(
            kg.store, meta["project_id"], meta["title"], meta["process_model"], cfg
        )
        with kg.transaction() as txn:
            for raw in operations:
                _apply_transact_op(txn, raw, project_iri, written_ids, delete_ids, counts)
        report = validate(kg.store, cfg)
        offending = _offends(report.violations, written_ids)
        if offending:
            with kg.transaction() as undo:
                for did in delete_ids:
                    undo.delete_entity(did, cascade=True)
            detail = "; ".join(f"{v.shape}: {v.message}" for v in offending)
            raise KGValidationError(f"transact failed validation: {detail}")

    return TransactResult(
        entities_written=counts["entities"],
        relations_written=counts["relations"],
        sections_written=counts["sections"],
    )


def _apply_transact_op(
    txn: TransactionContext,
    raw: dict[str, Any],
    project_iri: str,
    written_ids: set[str],
    delete_ids: list[str],
    counts: dict[str, int],
) -> None:
    op = raw.get("op")
    if op == "add_entity":
        _require_keys(raw, ("entity_id", "class", "title"), "add_entity")
        relations = [tuple(r) for r in raw.get("relations") or []]
        entity_id = raw["entity_id"]
        parent_id = raw.get("parent")
        iri = _stage_entity(
            txn,
            project_iri=project_iri,
            entity_id=entity_id,
            class_name=raw["class"],
            title=raw["title"],
            slots=raw.get("slots"),
            parent_id=parent_id,
            narrative=raw.get("narrative"),
            relations=relations,
            source_section=raw.get("section", ""),
        )
        written_ids.update({entity_id, iri})
        delete_ids.append(_scoped_delete_id(entity_id, parent_id))
        counts["entities"] += 1
        counts["relations"] += len(relations)
    elif op == "add_relation":
        _require_keys(raw, ("subject", "predicate", "object"), "add_relation")
        txn.add_relation(raw["subject"], raw["predicate"], raw["object"])
        counts["relations"] += 1
    elif op == "write_narrative":
        _require_keys(raw, ("doc_id", "anchor", "narrative"), "write_narrative")
        doc_id, anchor = raw["doc_id"], raw["anchor"]
        level = _existing_section_level(txn._store, txn._config, doc_id, anchor)
        body, resolved_level = _normalize_narrative(raw["narrative"], anchor, existing_level=level)
        txn.add_section(
            doc_id,
            anchor,
            body,
            _sha256(body),
            level=resolved_level,
            title=anchor,
            contained_entity_ids=raw.get("contained_entity_ids"),
        )
        counts["sections"] += 1
    else:
        raise KGValidationError(
            f"unknown transact op {op!r}; expected one of {', '.join(_TRANSACT_OPS)}"
        )


_PLACEHOLDER_RE = re.compile(r"\{[^}]*\}")


def _document_source_path(project_root: str, doc_type: str, doc_id: str) -> str:
    """Derive the project-root-relative source path ``docs/{subdir}/{id}.md``."""
    from cataforge.domain.docs.index_ops import _load_doc_type_map

    subdir = _load_doc_type_map(project_root).get(doc_type, doc_type)
    return f"docs/{subdir}/{doc_id}.md"


def author_document(
    project_root: str,
    markdown_text: str,
    *,
    source_path: str | None = None,
) -> AuthorDocumentResult:
    """Author a whole document (structure + entities + relations) into the graph.

    Requires ``context.mode = graph``. The frontmatter must carry ``doc_type``
    and ``id``; ``source_path`` defaults to ``docs/{subdir}/{id}.md`` (subdir
    resolved via the project's doc-type map). Structure, entities, and relations
    are extracted and staged into one transaction — the Document node, each
    Section (with its document-order ``position`` / heading ``level``), each
    entity (carrying its extracted ``content_hash`` / slots / parent scope), and
    each traceability edge. Any extracted entity title containing a ``{...}``
    placeholder is rejected (a template example must not pollute the graph);
    placeholders inside section bodies are allowed. A post-commit ``validate``
    pass compensates the whole write — document, sections, entities — to zero
    graph residue on any violation.
    """
    _require_graph_mode(project_root, "document authoring (`context write-doc`)")
    cfg = kg_config_for(project_root)
    meta = _read_project_metadata(Path(project_root))

    doc = parse_doc_text(
        markdown_text,
        doc_type="",
        file_name="authored.md",
        source_path=source_path or "authored.md",
        mtime=datetime.now(UTC).timestamp(),
    )
    if _PARSE_ERROR_KEY in doc.frontmatter:
        raise KGValidationError(
            f"document frontmatter YAML parse error: {doc.frontmatter[_PARSE_ERROR_KEY]}"
        )
    doc_type = doc.frontmatter.get("doc_type")
    if not isinstance(doc_type, str) or not doc_type:
        raise KGValidationError("document frontmatter must carry a non-empty 'doc_type'")
    doc_id = doc.frontmatter.get("id")
    if not isinstance(doc_id, str) or not doc_id:
        raise KGValidationError("document frontmatter must carry a non-empty 'id'")

    resolved_source_path = source_path or _document_source_path(project_root, doc_type, doc_id)
    doc.doc_id = doc_id
    doc.doc_type = doc_type
    doc.source_path = resolved_source_path

    entities = extract_entities(doc, authority=definition_authority(project_root))
    _guard_no_placeholder_titles(entities)
    document, sections = extract_structure(doc, entities)
    relations = extract_relations(doc)

    delete_ids = _author_document_delete_ids(doc_id, sections, entities)
    written_ids = {document_iri(doc_id, cfg.base_namespace)}

    with KnowledgeGraph.connect(cfg) as kg:
        project_iri = write_project(
            kg.store, meta["project_id"], meta["title"], meta["process_model"], cfg
        )
        with kg.transaction() as txn:
            txn.add_document(document)
            for section in sections:
                txn.add_section(
                    section.doc_id,
                    section.anchor,
                    section.narrative_body,
                    section.content_hash,
                    position=section.position,
                    level=section.level,
                    title=section.title,
                    contained_entity_ids=section.contained_entity_ids,
                )
            staged_iris = _stage_authored_entities(txn, entities, project_iri, written_ids)
            _stage_authored_relations(txn, relations, cfg, staged_iris)

        report = validate(kg.store, cfg)
        offending = _offends(report.violations, written_ids)
        if offending:
            with kg.transaction() as undo:
                for did in delete_ids:
                    undo.delete_entity(did, cascade=True)
            detail = "; ".join(f"{v.shape}: {v.message}" for v in offending)
            raise KGValidationError(f"authored document {doc_id} failed validation: {detail}")

    return AuthorDocumentResult(
        doc_id=doc_id,
        document_iri=document_iri(doc_id, cfg.base_namespace),
        sections_written=len(sections),
        entities_written=len(entities),
        relations_written=len(relations),
    )


def _guard_no_placeholder_titles(entities: list[ExtractedEntity]) -> None:
    offenders = [e.entity_id for e in entities if _PLACEHOLDER_RE.search(_entity_title(e))]
    if offenders:
        raise KGValidationError(
            "authored document carries placeholder entity title(s): "
            f"{', '.join(sorted(offenders))} — a template example entity must not be "
            "persisted into the graph."
        )


def _author_document_delete_ids(
    doc_id: str,
    sections: list[ExtractedSection],
    entities: list[ExtractedEntity],
) -> list[str]:
    """Compensating delete-target ids for a whole-document author write."""
    ids = [f"doc/{doc_id}/sec/{s.anchor}" for s in sections]
    ids.extend(_scoped_delete_id(e.entity_id, e.parent_id) for e in entities)
    ids.append(f"doc/{doc_id}")
    return ids


def _stage_authored_entities(
    txn: TransactionContext,
    entities: list[ExtractedEntity],
    project_iri: str,
    written_ids: set[str],
) -> dict[str, str]:
    """Stage each extracted entity; return a ``entity_id → staged IRI`` map."""
    staged_iris: dict[str, str] = {}
    for entity in entities:
        iri = txn.add_entity(
            entity.entity_id,
            entity.class_name,
            _entity_title(entity),
            entity.source_doc,
            entity.source_section,
            entity.content_hash,
            project_iri,
            parent_id=entity.parent_id,
            extra_slots=entity.extra_slots or None,
            mtime=entity.mtime,
        )
        staged_iris[entity.entity_id] = iri
        written_ids.add(entity.entity_id)
        written_ids.add(iri)
    return staged_iris


def _stage_authored_relations(
    txn: TransactionContext,
    relations: list[ExtractedRelation],
    cfg: Any,
    staged_iris: dict[str, str],
) -> None:
    """Stage each relation, resolving endpoints against the in-flight IRI map.

    Subordinate endpoints are not yet committed, so ``writer``'s store-querying
    resolution would miss them; the staged-IRI map is consulted first and the
    flat entity IRI is the fallback.
    """
    from cataforge.domain.kg.ingest.iri import entity_iri

    for relation in relations:
        subject_iri = staged_iris.get(relation.subject_entity_id) or entity_iri(
            relation.subject_entity_id, cfg.base_namespace
        )
        object_iri = staged_iris.get(relation.object_entity_id) or entity_iri(
            relation.object_entity_id, cfg.base_namespace
        )
        txn.add_relation(
            relation.subject_entity_id,
            relation.predicate_curie,
            relation.object_entity_id,
            subject_iri=subject_iri,
            object_iri=object_iri,
        )


def update_document_meta(
    project_root: str,
    doc_id: str,
    *,
    status: str | None = None,
    version: str | None = None,
) -> UpdateDocumentMetaResult:
    """Patch a Document's frontmatter ``status`` / ``version`` in the graph.

    Requires ``context.mode = graph``. The Document node must already exist.
    ``status`` is constrained to the doc-review whitelist. The stored
    ``frontmatter_raw`` is rewritten in place (preserving each line's original
    quote style; missing lines are inserted before the closing ``---``), the
    ``cf:status`` / ``cf:version`` slots are updated, and ``cf:content_hash`` is
    recomputed — all through one transaction.
    """
    _require_graph_mode(project_root, "document meta authoring (`context write-meta`)")
    if status is not None and status not in _DOC_STATUS_WHITELIST:
        raise KGValidationError(f"status {status!r} is not one of {sorted(_DOC_STATUS_WHITELIST)}")
    cfg = kg_config_for(project_root)
    with KnowledgeGraph.connect(cfg) as kg:
        current = _read_document_meta(kg.store, cfg, doc_id)
        if current is None:
            raise KGEntityNotFoundError(f"Document {doc_id!r} not found in store.")
        new_frontmatter = _patch_frontmatter(current["frontmatter_raw"], status, version)
        new_hash = _sha256(new_frontmatter + "\x1f" + current["preamble_body"])
        with kg.transaction() as txn:
            _stage_document_meta(
                txn,
                cfg,
                doc_id,
                frontmatter_raw=new_frontmatter,
                status=status,
                version=version,
                content_hash=new_hash,
            )
    return UpdateDocumentMetaResult(
        doc_id=doc_id,
        document_iri=document_iri(doc_id, cfg.base_namespace),
        status=status,
        version=version,
    )


_DOC_STATUS_WHITELIST = frozenset({"draft", "review", "approved"})


def _read_document_meta(store: ox.Store, cfg: Any, doc_id: str) -> dict[str, str] | None:
    """Read a Document's ``frontmatter_raw`` / ``preamble_body``, or ``None``."""
    ns = cf_namespace(cfg)
    iri = document_iri(doc_id, cfg.base_namespace)
    sparql = (
        f"PREFIX cf: <{ns}> "
        f"SELECT ?fm ?pre WHERE {{ <{assert_safe_iri(iri)}> a cf:Document . "
        f"OPTIONAL {{ <{assert_safe_iri(iri)}> cf:frontmatter_raw ?fm }} "
        f"OPTIONAL {{ <{assert_safe_iri(iri)}> cf:preamble_body ?pre }} }}"
    )
    for row in select_rows(store, sparql):
        return {
            "frontmatter_raw": _strv(_row_lookup(row, "fm")) or "",
            "preamble_body": _strv(_row_lookup(row, "pre")) or "",
        }
    return None


def _patch_frontmatter_line(frontmatter: str, key: str, value: str) -> str:
    """Replace ``key:``'s value (preserving quote style) or insert before ``---``."""
    line_re = re.compile(rf"^(?P<key>{re.escape(key)}:\s*)(?P<q>\"?)(?P<val>.*?)(?P=q)\s*$", re.M)
    match = line_re.search(frontmatter)
    if match is not None:
        quote = match.group("q")
        return line_re.sub(lambda _m: f"{match.group('key')}{quote}{value}{quote}", frontmatter, 1)
    return _insert_frontmatter_line(frontmatter, f"{key}: {value}")


def _insert_frontmatter_line(frontmatter: str, new_line: str) -> str:
    """Insert ``new_line`` just before the frontmatter's closing ``---`` fence."""
    lines = frontmatter.split("\n")
    fence_idxs = [i for i, ln in enumerate(lines) if ln.strip() == "---"]
    if len(fence_idxs) >= 2:
        lines.insert(fence_idxs[1], new_line)
        return "\n".join(lines)
    return frontmatter


def _patch_frontmatter(frontmatter: str, status: str | None, version: str | None) -> str:
    out = frontmatter
    if status is not None:
        out = _patch_frontmatter_line(out, "status", status)
    if version is not None:
        out = _patch_frontmatter_line(out, "version", version)
    return out


def _stage_document_meta(
    txn: TransactionContext,
    cfg: Any,
    doc_id: str,
    *,
    frontmatter_raw: str,
    status: str | None,
    version: str | None,
    content_hash: str,
) -> None:
    """Stage the slot rewrites for a Document meta patch."""
    import pyoxigraph as ox  # noqa: PLC0415

    ns = cf_namespace(cfg)
    iri = document_iri(doc_id, cfg.base_namespace)
    subject = ox.NamedNode(iri)
    string_dt = ox.NamedNode("http://www.w3.org/2001/XMLSchema#string")

    updates: list[tuple[str, str]] = [
        ("frontmatter_raw", frontmatter_raw),
        ("content_hash", content_hash),
    ]
    if status is not None:
        updates.append(("status", status))
    if version is not None:
        updates.append(("version", version))
    for slot, value in updates:
        pred = ox.NamedNode(f"{ns}{slot}")
        for q in list(txn._store.quads_for_pattern(subject, pred, None, None)):
            txn.remove(q)
        txn.add(ox.Quad(subject, pred, ox.Literal(value, datatype=string_dt)))


def finalize(project_root: str, output_dir: str | None = None) -> CompileResult | DocIndexResult:
    """Propagate authored content from its canonical source to derived views.

    Routed by :class:`~cataforge.domain.kg.authority.ModePolicy`:

    - ``markdown`` — the Markdown is canonical and there is no graph, so 定稿
      is a docs-index rebuild (``output_dir`` does not apply — the index lives
      in ``docs/``).
    - ``hybrid`` — the Markdown is canonical. 定稿 reflects it into the graph
      (md → KG) and rebuilds the docs index; it never re-exports graph → md,
      so hand edits to the authored Markdown are preserved.
    - ``graph`` — the graph is canonical and the Markdown is a derived view,
      reconstructed whole-document via ``compile_documents`` (frontmatter +
      preamble + section slices in document order, with orphan entities falling
      back to per-entity cards). An empty graph (no entities, no
      ``cf:Document`` nodes) means nothing has been authored yet, so there is
      nothing to export; an authored but entity-less Document (prose-only or
      early draft) is not empty and still exports.

    Either way the ``定稿`` contract routes persistence without the caller
    hand-running ``ingest``.
    """
    policy = ModePolicy.for_project(project_root)
    if not policy.graph_enabled:
        return _rebuild_doc_index(project_root)
    cfg = kg_config_for(project_root)
    out = Path(output_dir) if output_dir else Path(project_root) / "docs"
    if not policy.graph_is_source:  # hybrid — md is canonical, sync md → KG
        with KnowledgeGraph.connect(cfg) as kg:
            run_migration(kg.store, Path(project_root), cfg, doc_types=DEFAULT_DOC_TYPES)
        return _rebuild_doc_index(project_root)
    with KnowledgeGraph.connect(cfg) as kg:  # graph — KG is canonical, export → md
        if not kg.query.entity_ids() and not kg.query.has_documents():
            return CompileResult(exported_at=datetime.now(UTC), discovered_count=0, output_dir=out)
        result = compile_documents(kg.store, out)
    _rebuild_doc_index(project_root)
    return result


def ingest(
    project_root: str, doc_types: list[str] | None = None
) -> MigrationStats | DocIndexResult:
    """Reflect human-edited Markdown into the mode-selected backend.

    Under ``hybrid`` / ``graph`` this is the md → KG migration. Under
    ``markdown`` the Markdown already is the source of truth, so the equivalent
    is a full docs-index rebuild (``doc_types`` does not restrict it).
    """
    if not kg_enabled(project_root):
        return _rebuild_doc_index(project_root)
    cfg = kg_config_for(project_root)
    scope = tuple(doc_types) if doc_types else DEFAULT_DOC_TYPES
    with KnowledgeGraph.connect(cfg) as kg:
        stats, _entities, _relations = run_migration(
            kg.store, Path(project_root), cfg, doc_types=scope
        )
    return stats


def reconcile_check(project_root: str) -> ReconcileReport | DocValidationReport:
    """Drift guard between the Markdown tree and the mode-selected backend.

    Under ``hybrid`` / ``graph`` this reconciles the graph against the
    Markdown; under ``markdown`` it validates docs-index integrity
    (orphans / stale entries / xrefs / aliases / invalid ids).
    """
    if not kg_enabled(project_root):
        return _validate_doc_index(project_root)
    cfg = kg_config_for(project_root)
    with KnowledgeGraph.connect(cfg) as kg:
        return _reconcile(kg.store, Path(project_root), cfg)
