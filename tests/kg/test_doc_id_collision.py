"""Logical document id contract at scan.

Frontmatter ``id`` is the canonical logical-document key (matching templates,
write-doc, and finalize exports); filename inference is the fallback for
frontmatter-less files. One logical doc_id maps to one file — a batch where
multiple files resolve to the same doc_id is refused at scan, before any
write path can collapse Document nodes or cross-delete Sections.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.domain.kg import KGConfig, init_store
from cataforge.domain.kg._errors import KGDocumentCollisionError
from cataforge.domain.kg.ingest import run_migration
from cataforge.domain.kg.ingest.scan import parse_doc_text, scan_business_docs


def _parse(raw: str, file_name: str = "dev-plan.md") -> object:
    return parse_doc_text(
        raw,
        doc_type="dev-plan",
        file_name=file_name,
        source_path=f"docs/dev-plan/{file_name}",
        mtime=0.0,
    )


def _write(project_root: Path, doc_type: str, name: str, body: str) -> None:
    d = project_root / "docs" / doc_type
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def _count(store, sparql: str) -> int:
    rows = list(store.query(sparql))
    return int(rows[0]["n"].value) if rows and rows[0]["n"] is not None else 0


def _typed_count(store, config: KGConfig, cls: str) -> int:
    ns = config.ontology_namespace.rstrip("/") + "/"
    return _count(
        store,
        f"PREFIX cf: <{ns}> SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE {{ ?s a cf:{cls} }}",
    )


# --- frontmatter key contract -------------------------------------------------


def test_parse_doc_text_reads_frontmatter_id() -> None:
    doc = _parse(
        "---\nid: sprint-plan\ndoc_type: dev-plan\n---\n# 计划\n",
        file_name="dev-plan-sprint.md",
    )
    assert doc.doc_id == "sprint-plan"


def test_parse_doc_text_without_id_infers_from_filename() -> None:
    doc = _parse("# 计划\n")
    assert doc.doc_id == "dev-plan"


def test_parse_doc_text_has_no_doc_id_key_support() -> None:
    # No framework surface (templates / write-doc / finalize) ever emits a
    # `doc_id` frontmatter key; the reader must not resurrect it.
    doc = _parse("---\ndoc_id: custom-plan\n---\n# 计划\n")
    assert doc.doc_id == "dev-plan"


def test_parse_doc_text_non_string_id_falls_back_to_inference() -> None:
    doc = _parse("---\nid: 42\n---\n# 计划\n")
    assert doc.doc_id == "dev-plan"


_DOC_A = "---\nid: dev-plan-a\n---\n# 甲\n\n## §1 一\n\n甲。\n"
_DOC_B = "---\nid: dev-plan-b\n---\n# 乙\n\n## §1 一\n\n乙。\n"


def test_scan_preserves_distinct_frontmatter_ids(tmp_path: Path) -> None:
    _write(tmp_path, "dev-plan", "dev-plan-a.md", _DOC_A)
    _write(tmp_path, "dev-plan", "dev-plan-b.md", _DOC_B)

    parsed = scan_business_docs(tmp_path, ["dev-plan"])

    assert sorted(d.doc_id for d in parsed) == ["dev-plan-a", "dev-plan-b"]


def test_ingest_preserves_distinct_document_nodes(tmp_path: Path) -> None:
    _write(tmp_path, "dev-plan", "dev-plan-a.md", _DOC_A)
    _write(tmp_path, "dev-plan", "dev-plan-b.md", _DOC_B)
    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)

    run_migration(handle.raw, tmp_path, config, doc_types=("dev-plan",))

    assert _typed_count(handle.raw, config, "Document") == 2


# --- collision refusal at scan ------------------------------------------------


def test_scan_refuses_colliding_doc_ids(tmp_path: Path) -> None:
    # Frontmatter-less: filename inference maps both dev-plan-*.md to `dev-plan`.
    _write(tmp_path, "dev-plan", "dev-plan-a.md", "# 甲\n\n## §1 一\n\n甲。\n")
    _write(tmp_path, "dev-plan", "dev-plan-b.md", "# 乙\n\n## §1 一\n\n乙。\n")

    with pytest.raises(KGDocumentCollisionError) as excinfo:
        scan_business_docs(tmp_path, ["dev-plan"])

    msg = str(excinfo.value)
    assert "dev-plan-a.md" in msg and "dev-plan-b.md" in msg
    assert "id" in msg
    (collision,) = excinfo.value.collisions
    assert collision.doc_id == "dev-plan"
    assert len(collision.source_paths) == 2


def test_scan_collision_ignores_entity_cards(tmp_path: Path) -> None:
    # A per-entity card export (frontmatter `entity_id`) is a derived render,
    # not a logical document claim — its inferred doc_id must not collide.
    _write(tmp_path, "dev-plan", "dev-plan.md", "# 计划\n\n## §1 一\n\n甲。\n")
    _write(
        tmp_path,
        "dev-plan",
        "dev-plan-T-001.md",
        "---\nentity_id: T-001\ntitle: 任务\nsort_key: T-001\n---\n# T-001 — 任务\n",
    )

    parsed = scan_business_docs(tmp_path, ["dev-plan"])

    assert len(parsed) == 2


def test_migration_refuses_collision_store_untouched(tmp_path: Path) -> None:
    _write(tmp_path, "dev-plan", "dev-plan-a.md", "# 甲\n\n## §1 一\n\n甲。\n")
    _write(tmp_path, "dev-plan", "dev-plan-b.md", "# 乙\n\n## §1 一\n\n乙。\n")
    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)

    with pytest.raises(KGDocumentCollisionError):
        run_migration(handle.raw, tmp_path, config, doc_types=("dev-plan",))

    assert _typed_count(handle.raw, config, "Document") == 0
    assert _typed_count(handle.raw, config, "Section") == 0


def test_repair_refuses_collision_and_leaves_sections_intact(tmp_path: Path) -> None:
    from cataforge.domain.kg.repair import repair

    _write(
        tmp_path,
        "dev-plan",
        "dev-plan.md",
        "# 计划\n\n## §1 一\n\n甲。\n\n## §2 二\n\n乙。\n",
    )
    config = KGConfig(store_backend="memory", kg_active_doc_types={"dev-plan"})
    handle = init_store(config, force=True)
    run_migration(handle.raw, tmp_path, config, doc_types=("dev-plan",))
    sections_before = _typed_count(handle.raw, config, "Section")
    assert sections_before >= 2

    # A second file claiming the same logical document appears on disk.
    _write(tmp_path, "dev-plan", "dev-plan-hotfix.md", "# 补\n\n## §9 九\n\n补。\n")

    with pytest.raises(KGDocumentCollisionError):
        repair(handle.raw, tmp_path, config)

    assert _typed_count(handle.raw, config, "Section") == sections_before


def test_reconcile_marks_collision_doc_type_documents_manual(tmp_path: Path) -> None:
    # A collision makes the whole doc_type's FS side unreliable — drift
    # records for its stored documents must demand a human decision instead
    # of recommending an automatic export/ingest that would act on bad data.
    from cataforge.domain.kg.reconcile import reconcile

    _write(tmp_path, "dev-plan", "dev-plan.md", "# 计划\n\n## §1 一\n\n甲。\n")
    config = KGConfig(store_backend="memory", kg_active_doc_types={"dev-plan"})
    handle = init_store(config, force=True)
    run_migration(handle.raw, tmp_path, config, doc_types=("dev-plan",))

    _write(tmp_path, "dev-plan", "dev-plan-b.md", "# 乙\n\n## §1 一\n\n乙。\n")
    report = reconcile(handle.raw, tmp_path, config)

    records = [d for d in report.documents if d.source_path == "docs/dev-plan/dev-plan.md"]
    assert records and all(d.remediation == "manual" for d in records), [
        d.to_dict() for d in report.documents
    ]


# --- reconcile surfaces the collision as a finding -----------------------------


def test_reconcile_reports_collision_without_crashing(tmp_path: Path) -> None:
    from cataforge.domain.kg.reconcile import reconcile

    _write(tmp_path, "dev-plan", "dev-plan-a.md", "# 甲\n\n## §1 一\n\n甲。\n")
    _write(tmp_path, "dev-plan", "dev-plan-b.md", "# 乙\n\n## §1 一\n\n乙。\n")
    config = KGConfig(store_backend="memory", kg_active_doc_types={"dev-plan"})
    handle = init_store(config, force=True)

    report = reconcile(handle.raw, tmp_path, config)

    per = report.per_doc_type["dev-plan"]
    (collision,) = per.doc_id_collisions
    assert collision.doc_id == "dev-plan"
    assert report.ok is False
    payload = per.to_dict()
    assert payload["doc_id_collisions"] == [
        {
            "doc_id": "dev-plan",
            "source_paths": [
                "docs/dev-plan/dev-plan-a.md",
                "docs/dev-plan/dev-plan-b.md",
            ],
        }
    ]
