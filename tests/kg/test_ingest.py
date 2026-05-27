"""End-to-end ingest tests on the waterfall + agile fixtures.

The fixtures (`tests/fixtures/kg-vertical-slice/{waterfall,agile}`) are
the verifiable-condition workhorse for task-7 §7.1 sub-PR 3 exit
("`cataforge kg validate` with zero `missing` entries on a hand-crafted
fixture project covering both waterfall and agile process models").
"""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"
VARIANTS = ("waterfall", "agile")

def _open_memory_store():
    from cataforge.kg import KGConfig
    from cataforge.kg.store import init_store

    config = KGConfig(store_backend="memory")
    return init_store(config, force=True), config

@pytest.mark.parametrize("variant", VARIANTS)
def test_codemod_end_to_end(variant: str) -> None:
    from cataforge.kg.ingest import run_migration

    handle, config = _open_memory_store()
    root = FIXTURE_ROOT / variant

    stats, entities, relations = run_migration(handle.raw, root, config)

    # Parse-side
    assert stats.parsed_docs == 3, f"{variant}: expected 3 docs, got {stats.parsed_docs}"
    extracted_ids = {e.entity_id for e in entities}
    assert extracted_ids == {
        "F-001", "F-002",
        "AC-001", "AC-002",
        "M-001", "M-002",
        "TC-001", "TC-002",
        "TS-001",
    }, f"{variant}: unexpected entity set: {extracted_ids}"

    # Relation-side
    rel_keys = {
        (r.subject_entity_id, r.predicate_curie, r.object_entity_id)
        for r in relations
    }
    assert rel_keys == {
        ("M-001", "cf:implements", "F-001"),
        ("M-002", "cf:implements", "F-002"),
        ("TC-001", "cf:verifies", "AC-001"),
        ("TC-002", "cf:verifies", "AC-002"),
    }, f"{variant}: unexpected relations: {rel_keys}"

    # Write-side
    assert stats.write_stats.entities_written == 9
    assert stats.write_stats.relations_written == 4
    assert stats.write_stats.entities_skipped == 0
    assert stats.write_stats.relations_skipped == 0

    # Verify-side
    assert stats.verify_result is not None
    assert stats.verify_result.ok, (
        f"{variant}: verify failed: missing={stats.verify_result.missing_entities} "
        f"hash_mismatch={stats.verify_result.content_hash_mismatches}"
    )

@pytest.mark.parametrize("variant", VARIANTS)
def test_codemod_is_idempotent(variant: str) -> None:
    from cataforge.kg.ingest import run_migration

    handle, config = _open_memory_store()
    root = FIXTURE_ROOT / variant

    first, _, _ = run_migration(handle.raw, root, config)
    assert first.write_stats.entities_written == 9
    assert first.write_stats.relations_written == 4

    second, _, _ = run_migration(handle.raw, root, config)
    assert second.write_stats.entities_written == 0, (
        f"{variant}: re-run wrote {second.write_stats.entities_written} "
        "entities; content hash dedup not working"
    )
    assert second.write_stats.relations_written == 0, (
        f"{variant}: re-run wrote {second.write_stats.relations_written} relations"
    )
    assert second.write_stats.entities_skipped == 9
    assert second.write_stats.relations_skipped == 4
    assert second.verify_result is not None and second.verify_result.ok

@pytest.mark.parametrize("variant", VARIANTS)
def test_dry_run_does_not_write(variant: str) -> None:
    from cataforge.kg.ingest import run_migration

    handle, config = _open_memory_store()
    root = FIXTURE_ROOT / variant

    stats, entities, relations = run_migration(
        handle.raw, root, config, dry_run=True
    )

    assert stats.dry_run is True
    assert stats.write_stats.entities_written == 0
    assert stats.write_stats.relations_written == 0
    assert stats.extracted_entities == 9
    assert stats.extracted_relations == 4
    # Graph is still empty of business data — verify reports everything missing.
    assert stats.verify_result is not None
    assert len(stats.verify_result.missing_entities) == 9

def test_xref_inside_arch_does_not_pollute_arch_entity_set() -> None:
    """Regression: ENTITY_PREFIX_RE used to capture `F-001` from
    `prd#§2.F-001` inside arch, attributing the Feature to arch's
    Module heading. Fix lives in entity_extract._inside_xref."""
    from cataforge.kg.ingest import extract_entities, scan_business_docs

    docs = scan_business_docs(FIXTURE_ROOT / "waterfall", ["arch"])
    assert len(docs) == 1
    entities = extract_entities(docs[0])
    entity_ids = {e.entity_id for e in entities}
    assert entity_ids == {"M-001", "M-002", "TS-001"}, (
        f"arch should only define M-NNN/TS-NNN entities; got {entity_ids}"
    )

@pytest.mark.parametrize("variant", VARIANTS)
def test_project_node_records_process_model(variant: str) -> None:
    """Round-2 decision: waterfall + agile both write through the codemod.
    Project node must carry the right cf:process_model literal so sub-PR 5
    can branch on it without reparsing framework.json."""
    from cataforge.kg.ingest import run_migration

    handle, config = _open_memory_store()
    root = FIXTURE_ROOT / variant
    run_migration(handle.raw, root, config)

    rows = list(
        handle.raw.query(
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "SELECT ?proj ?pm WHERE { ?proj a cf:Project ; cf:process_model ?pm }"
        )
    )
    assert len(rows) == 1, f"{variant}: expected exactly one Project node, got {len(rows)}"
    assert rows[0]["pm"].value == variant

@pytest.mark.parametrize("variant", VARIANTS)
def test_validate_reports_zero_violations_after_clean_import(variant: str) -> None:
    from cataforge.kg.ingest import run_migration
    from cataforge.kg.validate import validate

    handle, config = _open_memory_store()
    root = FIXTURE_ROOT / variant
    run_migration(handle.raw, root, config)

    report = validate(handle.raw, config)
    assert report.ok, (
        f"{variant}: validate flagged violations on a clean fixture:\n"
        + "\n".join(f"  {v.severity} {v.entity_id} {v.shape}: {v.message}"
                    for v in report.violations)
    )
