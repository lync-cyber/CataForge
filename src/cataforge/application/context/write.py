"""KG-first authoring — the write side of the context lifecycle.

In ``kg-first`` mode the knowledge graph is the source of truth: authoring
writes go to the graph under write-time schema validation, then Markdown
is *exported* as a human-review view (``finalize``). Human edits to the
exported Markdown are reflected back with ``ingest``, and ``reconcile``
guards the two against drift.

This inverts the legacy ``write md → kg import`` projection: structured
entities and prose are authored into the graph first (validated), and the
file tree is derived from them.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cataforge.domain.kg import KnowledgeGraph
from cataforge.domain.kg._dispatch import kg_config_for
from cataforge.domain.kg._errors import KGValidationError
from cataforge.domain.kg.export import compile_to_markdown, entity_doc_type
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

    Validates before and after the write: the entity_id↔class gate runs
    up front, and a post-commit ``validate`` pass compensates (deletes the
    just-written entity) and raises if it introduced any violation.
    """
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
    """Author a Section's prose (``narrative_body``) directly into the graph."""
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


def finalize(project_root: str, output_dir: str | None = None) -> CompileResult:
    """Persist authored content and return the export view (KG → md).

    Two authoring modes converge here. ``context write`` authors into the
    graph, so the graph is canonical and the Markdown is a derived view —
    exported here. Markdown-first authoring edits the files directly, leaving
    the graph empty; that Markdown is canonical, so it is seeded into the graph
    (md → KG) and kept as-is. The empty-graph branch deliberately does NOT
    re-export: ``compile_to_markdown`` is a lossy round-trip (it drops authored
    relation/section content), so exporting over the source would degrade it.
    Either way the ``定稿`` contract routes persistence without the caller
    hand-running ``ingest``.
    """
    cfg = kg_config_for(project_root)
    out = Path(output_dir) if output_dir else Path(project_root) / "docs"
    with KnowledgeGraph.connect(cfg) as kg:
        if not kg.query.entity_ids():
            run_migration(kg.store, Path(project_root), cfg, doc_types=DEFAULT_DOC_TYPES)
            return CompileResult(exported_at=datetime.now(UTC), discovered_count=0, output_dir=out)
        return compile_to_markdown(kg.store, out)


def ingest(project_root: str, doc_types: list[str] | None = None) -> MigrationStats:
    """Reflect human-edited Markdown back into the graph (md → KG)."""
    cfg = kg_config_for(project_root)
    scope = tuple(doc_types) if doc_types else DEFAULT_DOC_TYPES
    with KnowledgeGraph.connect(cfg) as kg:
        stats, _entities, _relations = run_migration(
            kg.store, Path(project_root), cfg, doc_types=scope
        )
    return stats


def reconcile_check(project_root: str) -> ReconcileReport:
    """Drift guard between the graph and the exported Markdown."""
    cfg = kg_config_for(project_root)
    with KnowledgeGraph.connect(cfg) as kg:
        return _reconcile(kg.store, Path(project_root), cfg)
