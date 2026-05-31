"""Phase 1b — ingest emits Document/Section structural nodes + drift coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _build_store(variant: str = "waterfall"):
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    stats, _ents, _rels = run_migration(handle.raw, FIXTURE_ROOT / variant, config)
    return handle, config, stats


def _count(store, sparql: str) -> int:
    rows = list(store.query(sparql))
    return int(rows[0]["n"].value) if rows and rows[0]["n"] is not None else 0


def test_import_writes_document_and_section_nodes() -> None:
    handle, config, stats = _build_store()
    ns = config.ontology_namespace.rstrip("/") + "/"

    def _typed(cls: str) -> int:
        return _count(
            handle.raw,
            f"PREFIX cf: <{ns}> SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE {{ ?s a cf:{cls} }}",
        )

    docs = _typed("Document")
    secs = _typed("Section")
    assert docs == 3, f"expected one Document per doc, got {docs}"
    assert secs == stats.structure_stats.sections_written > 0
    assert stats.structure_stats.documents_written == 3


def test_section_carries_prose_and_containment() -> None:
    handle, config, _stats = _build_store()
    ns = config.ontology_namespace.rstrip("/") + "/"
    # F-001's owning section must hold narrative_body and contain F-001.
    has_prose = _count(
        handle.raw,
        f"PREFIX cf: <{ns}> SELECT (COUNT(*) AS ?n) WHERE {{ "
        "?s a cf:Section ; cf:contains_entity ?e ; cf:narrative_body ?b . "
        '?e cf:entity_id "F-001" }',
    )
    assert has_prose >= 1


def test_structure_write_is_idempotent() -> None:
    from cataforge.domain.kg.ingest import run_migration

    handle, config, _first = _build_store()
    second, _e, _r = run_migration(handle.raw, FIXTURE_ROOT / "waterfall", config)
    assert second.structure_stats.documents_written == 0
    assert second.structure_stats.sections_written == 0
    assert second.structure_stats.documents_skipped == 3
    assert second.structure_stats.sections_skipped > 0


def test_reconcile_clean_after_structure_ingest() -> None:
    from cataforge.domain.kg.reconcile import reconcile

    handle, config, _stats = _build_store()
    report = reconcile(handle.raw, FIXTURE_ROOT / "waterfall", config)
    for per in report.per_doc_type.values():
        assert per.missing_sections == [], per.to_dict()
        assert per.ghost_sections == [], per.to_dict()
    assert report.ok, report.to_dict()


def test_structural_nodes_excluded_from_entity_export(tmp_path: Path) -> None:
    """Document/Section have no cf:entity_id → export must ignore them."""
    from cataforge.domain.kg.export import compile_to_markdown

    handle, _config, _stats = _build_store()
    result = compile_to_markdown(handle.raw, tmp_path / "out")
    assert not result.errors
    rendered = {rec.output_path.name for rec in result.file_records}
    assert all(not name.startswith("doc-") for name in rendered)


@pytest.mark.parametrize("variant", ["waterfall", "agile"])
def test_structure_survives_both_variants(variant: str) -> None:
    _handle, _config, stats = _build_store(variant)
    assert stats.structure_stats.documents_written >= 1
    assert stats.structure_stats.sections_written >= 1
