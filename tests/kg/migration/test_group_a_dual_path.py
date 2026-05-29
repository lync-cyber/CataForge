"""Golden-file regression: Group A call sites under KG vs legacy paths.

Task 7 §7.1 sub-PR 5 exit-condition requirement: "All 15 Group A call
points return identical results via KG path as legacy path on the
fixture project (one-shot regression test recorded as a golden file)."

Equivalence here is **structural**, not byte-identical: KG returns
dicts with typed slots while the legacy loader returns raw markdown
text. The contract verified by these tests is:

* Same entity_id is discoverable through both paths.
* Same set of entities is enumerated by both paths.
* Per-Feature implementation/test coverage agrees.
* The graph eliminates the regex false-positive class (Task 1 §1.4
  case A) — see :mod:`test_a13_bidirectional_coverage` for that
  specific assassination test.

Tests are parametrized over both fixture variants (waterfall + agile)
to satisfy the Alpha exit condition that *both* process-model paths
pass end-to-end.
"""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "kg-vertical-slice"
VARIANTS = ("waterfall", "agile")

def _ingest_into_memory(project_root: Path):
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, project_root, config)
    kg = KnowledgeGraph(handle.raw, config)
    return kg, config

# ---------------------------------------------------------------------------
# Group A entity-id discovery dual-path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", VARIANTS)
def test_entity_id_set_matches_legacy_scan(variant: str) -> None:
    """The KG path's entity_ids() must enumerate the same IDs the
    legacy filesystem scan finds. Mismatches mean either the ingest
    missed entities (KG ⊂ FS) or the graph holds stale entities
    (KG ⊃ FS) — both are doctor gate failure modes.
    """
    from cataforge.interface.cli.doctor.kg_ingestion import _scan_fs_entity_ids

    project_root = FIXTURE_ROOT / variant
    kg, _ = _ingest_into_memory(project_root)

    fs_ids = _scan_fs_entity_ids(
        project_root,
        {"prd", "arch", "test"},
        {"prd": "prd", "arch": "arch", "test": "test-report"},
    )
    kg_ids = kg.query.entity_ids()

    assert fs_ids == kg_ids, (
        f"FS-only: {fs_ids - kg_ids}; KG-only: {kg_ids - fs_ids}"
    )

# ---------------------------------------------------------------------------
# A2 / A5 — typed accessors return non-null on existing entities
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", VARIANTS)
def test_typed_accessors_locate_known_entities(variant: str) -> None:
    project_root = FIXTURE_ROOT / variant
    kg, _ = _ingest_into_memory(project_root)

    assert kg.query.feature("F-001") is not None
    assert kg.query.feature("F-002") is not None
    assert kg.query.module("M-001") is not None
    assert kg.query.test_case("TC-001") is not None
    # Errata C1: api() / page() exposed even when fixture has no instances
    assert kg.query.api("API-999") is None
    assert kg.query.page("P-999") is None

# ---------------------------------------------------------------------------
# A13 — bidirectional coverage agrees with TraceAPI.bidirectional_coverage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", VARIANTS)
def test_bidirectional_coverage_reflects_graph_edges(variant: str) -> None:
    """TraceAPI.bidirectional_coverage must report the implementation
    edges present in the fixture without false positives. The fixture
    has Module cf:implements F-001/F-002 but NO TestCase cf:verifies
    targeting Features directly (TCs verify ACs).
    """
    project_root = FIXTURE_ROOT / variant
    kg, _ = _ingest_into_memory(project_root)

    rows = kg.trace.bidirectional_coverage()
    by_id = {r.feature_id: r for r in rows}

    assert {"F-001", "F-002"} <= set(by_id)
    for fid in ("F-001", "F-002"):
        assert by_id[fid].has_impl is True
        # No direct TC→Feature edge in fixture; the regex-only legacy
        # check would falsely register coverage on string mention.
        assert by_id[fid].has_test is False

# ---------------------------------------------------------------------------
# Both process-model paths reach the same exit shape
# ---------------------------------------------------------------------------

def test_waterfall_and_agile_produce_identical_entity_set() -> None:
    """Alpha exit condition: both process_model = waterfall and = agile
    pass end-to-end on the fixture project (Task 7 §7.1 exit).
    """
    kg_wf, _ = _ingest_into_memory(FIXTURE_ROOT / "waterfall")
    kg_ag, _ = _ingest_into_memory(FIXTURE_ROOT / "agile")

    assert kg_wf.query.entity_ids() == kg_ag.query.entity_ids()
