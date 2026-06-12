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
from typing import TYPE_CHECKING

from cataforge.core.errors import CataforgeError
from cataforge.domain.kg import KnowledgeGraph
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


class ContextStrategyError(CataforgeError):
    """Raised when an operation needs a backend the project's
    ``context.strategy`` does not enable."""


@dataclass(frozen=True)
class DocIndexResult:
    """Outcome of a lifecycle write routed to the docs-index backend."""

    indexed_count: int
    index_path: Path


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


def author_entity(
    project_root: str,
    *,
    entity_id: str,
    class_name: str,
    title: str,
    slots: dict[str, str] | None = None,
    source_section: str = "",
    project_id: str | None = None,
) -> str:
    """Authorize-and-write one entity to the graph; return its IRI.

    Requires the ``kg-first`` strategy. Validates before and after the
    write: the entity_id↔class gate runs up front, and a post-commit
    ``validate`` pass compensates (deletes the just-written entity) and
    raises if it introduced any violation.
    """
    _require_kg_first(project_root, "entity authoring (`context write`)")
    _check_entity_class(entity_id, class_name)
    cfg = kg_config_for(project_root)
    meta = _read_project_metadata(Path(project_root))
    pid = project_id or meta["project_id"]
    extra = {f"cf:{k}": v for k, v in (slots or {}).items()} or None
    slot_digest = "\x1f".join(f"{k}={v}" for k, v in sorted((slots or {}).items()))
    content_hash = _sha256(f"{title}\x1f{slot_digest}")
    source_doc = entity_doc_type(class_name)

    with KnowledgeGraph.connect(cfg) as kg:
        project_iri = write_project(kg.store, pid, meta["title"], meta["process_model"], cfg)
        with kg.transaction() as txn:
            iri = txn.add_entity(
                entity_id,
                class_name,
                title,
                source_doc,
                source_section,
                content_hash,
                project_iri,
                extra_slots=extra,
            )
        report = validate(kg.store, cfg)
        offending = [v for v in report.violations if v.entity_id in (entity_id, iri)]
        if offending:
            with kg.transaction() as undo:
                undo.delete_entity(entity_id, cascade=True)
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
        return compile_documents(kg.store, out)


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
