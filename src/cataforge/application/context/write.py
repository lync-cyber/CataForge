"""Strategy-routed authoring — the write side of the context lifecycle.

Each lifecycle operation routes on the project's ``context.strategy``.
Under ``kg-first`` the knowledge graph is the source of truth: authoring
writes go to the graph under write-time schema validation, then Markdown
is *exported* as a human-review view (``finalize``); human edits to the
exported Markdown are reflected back with ``ingest``, and ``reconcile``
guards the two against drift. Under ``doc-only`` Markdown is the source:
``finalize`` / ``ingest`` rebuild the docs index, ``reconcile`` validates
its integrity, and entity/narrative authoring is rejected as a
configuration error.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cataforge.core.errors import CataforgeError
from cataforge.domain.kg import KnowledgeGraph
from cataforge.domain.kg._content_hash import entity_content_hash
from cataforge.domain.kg._dispatch import kg_config_for, kg_enabled
from cataforge.domain.kg._errors import KGValidationError
from cataforge.domain.kg.export import entity_doc_type
from cataforge.domain.kg.export.document_pipeline import compile_documents
from cataforge.domain.kg.export.types import CompileResult
from cataforge.domain.kg.ingest import DEFAULT_DOC_TYPES, run_migration
from cataforge.domain.kg.ingest.iri import id_prefix_to_type
from cataforge.domain.kg.ingest.migrate import _read_project_metadata
from cataforge.domain.kg.ingest.structure_extract import ExtractedSection
from cataforge.domain.kg.ingest.writer import write_project, write_structure
from cataforge.domain.kg.reconcile import reconcile as _reconcile
from cataforge.domain.kg.validate import validate

if TYPE_CHECKING:
    from cataforge.domain.kg.ingest.migrate import MigrationStats
    from cataforge.domain.kg.reconcile import ReconcileReport
    from cataforge.domain.kg.transaction import TransactionContext
    from cataforge.domain.kg.validate import ValidationViolation


class ContextStrategyError(CataforgeError):
    """Raised when an operation needs a backend the project's
    ``context.strategy`` does not enable."""


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


def _require_kg_first(project_root: str, capability: str) -> None:
    if kg_enabled(project_root):
        return
    raise ContextStrategyError(
        f"{capability} authors into the knowledge graph and requires "
        'context.strategy = "kg-first" in .cataforge/framework.json; '
        "this project resolves to a Markdown-only strategy — "
        "edit the documents under docs/ directly instead."
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
) -> str:
    """Stage one entity (with slots / narrative / outgoing edges) into ``txn``.

    Returns the entity IRI. The entity_id↔class gate runs first.
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
        entity_doc_type(class_name),
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

    Requires the ``kg-first`` strategy. A subordinate ``parent_id`` yields a
    parent-scoped IRI plus a ``cf:part_of`` edge; ``relations`` add outgoing
    traceability edges; ``narrative`` is stored as the ``cf:narrative_body``
    slot — all in one transaction. The entity_id↔class gate runs up front, and
    a post-commit ``validate`` pass compensates (deletes the just-written
    entity and its edges) and raises if it introduced any violation.
    """
    _require_kg_first(project_root, "entity authoring (`context write`)")
    cfg = kg_config_for(project_root)
    meta = _read_project_metadata(Path(project_root))
    pid = project_id or meta["project_id"]

    with KnowledgeGraph.connect(cfg) as kg:
        project_iri = write_project(kg.store, pid, meta["title"], meta["process_model"], cfg)
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

    Requires the ``kg-first`` strategy.
    """
    _require_kg_first(project_root, "narrative authoring (`context write-narrative`)")
    cfg = kg_config_for(project_root)
    section = ExtractedSection(
        doc_id=doc_id,
        anchor=anchor,
        title=anchor,
        narrative_body=narrative,
        content_hash=_sha256(narrative),
        source_doc=doc_id,
        contained_entity_ids=sorted(contained_entity_ids or []),
    )
    with KnowledgeGraph.connect(cfg) as kg:
        write_structure(kg.store, [], [section], cfg)


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
    object), or ``write_narrative`` (doc_id / anchor / narrative). Requires the
    ``kg-first`` strategy. All ops stage into one ``TransactionContext`` and
    commit together; a post-commit ``validate`` over the written entities
    compensates the whole batch on any violation — zero graph residue.
    """
    _require_kg_first(project_root, "batch authoring (`context transact`)")
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
        txn.add_section(
            raw["doc_id"],
            raw["anchor"],
            raw["narrative"],
            _sha256(raw["narrative"]),
            contained_entity_ids=raw.get("contained_entity_ids"),
        )
        counts["sections"] += 1
    else:
        raise KGValidationError(
            f"unknown transact op {op!r}; expected one of {', '.join(_TRANSACT_OPS)}"
        )


def finalize(project_root: str, output_dir: str | None = None) -> CompileResult | DocIndexResult:
    """Persist authored content via the strategy-selected backend.

    Under ``doc-only`` the Markdown is the source of truth, so 定稿 is a
    docs-index rebuild (``output_dir`` does not apply — the index lives in
    ``docs/``). Under ``kg-first`` two authoring modes converge here.
    ``context write`` authors into the graph, so the graph is canonical and
    the Markdown is a derived view — reconstructed whole-document via
    ``compile_documents`` (frontmatter + preamble + section slices in
    document order, with orphan entities falling back to per-entity cards).
    Markdown-first authoring edits the files directly, leaving the graph
    empty; that Markdown is canonical, so it is seeded into the graph
    (md → KG) and kept as-is — the empty-graph branch seeds without
    re-exporting over the source. Either way the ``定稿`` contract routes
    persistence without the caller hand-running ``ingest``.
    """
    if not kg_enabled(project_root):
        return _rebuild_doc_index(project_root)
    cfg = kg_config_for(project_root)
    out = Path(output_dir) if output_dir else Path(project_root) / "docs"
    with KnowledgeGraph.connect(cfg) as kg:
        if not kg.query.entity_ids():
            run_migration(kg.store, Path(project_root), cfg, doc_types=DEFAULT_DOC_TYPES)
            return CompileResult(exported_at=datetime.now(UTC), discovered_count=0, output_dir=out)
        result = compile_documents(kg.store, out)
    _rebuild_doc_index(project_root)
    return result


def ingest(
    project_root: str, doc_types: list[str] | None = None
) -> MigrationStats | DocIndexResult:
    """Reflect human-edited Markdown into the strategy-selected backend.

    Under ``kg-first`` this is the md → KG migration. Under ``doc-only``
    the Markdown already is the source of truth, so the equivalent is a
    full docs-index rebuild (``doc_types`` does not restrict it).
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
    """Drift guard between the Markdown tree and the strategy-selected backend.

    Under ``kg-first`` this reconciles the graph against the exported
    Markdown; under ``doc-only`` it validates docs-index integrity
    (orphans / stale entries / xrefs / aliases / invalid ids).
    """
    if not kg_enabled(project_root):
        return _validate_doc_index(project_root)
    cfg = kg_config_for(project_root)
    with KnowledgeGraph.connect(cfg) as kg:
        return _reconcile(kg.store, Path(project_root), cfg)
