"""Tests for KG repair."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pyoxigraph_installed = importlib.util.find_spec("pyoxigraph") is not None
linkml_runtime_installed = importlib.util.find_spec("linkml_runtime") is not None

pytestmark = pytest.mark.skipif(
    not (pyoxigraph_installed and linkml_runtime_installed),
    reason="kg extra not installed (pyoxigraph + linkml-runtime)",
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _make_populated_store(variant: str = "waterfall"):
    from cataforge.kg import KGConfig, init_store
    from cataforge.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, FIXTURE_ROOT / variant, config)
    return handle, config


def test_repair_on_clean_store_is_noop() -> None:
    from cataforge.kg.repair import repair

    handle, config = _make_populated_store()
    stats = repair(handle.raw, FIXTURE_ROOT / "waterfall", config)
    assert stats.ghosts_removed == 0
    assert stats.missing_ingested == 0
    assert not stats.errors


def test_repair_removes_ghost_entity() -> None:
    from cataforge.kg._quads import build_entity_quads
    from cataforge.kg.ingest.iri import entity_iri
    from cataforge.kg.reconcile import reconcile
    from cataforge.kg.repair import repair

    handle, config = _make_populated_store()
    store = handle.raw

    project_iri = entity_iri("proj-default", config.base_namespace)
    for q in build_entity_quads(
        entity_id="F-999",
        class_name="Feature",
        title="Ghost feature",
        source_doc="prd",
        source_section="F-999 Ghost",
        content_hash="ghost_hash",
        project_iri=project_iri,
        config=config,
    ):
        store.add(q)

    report_before = reconcile(store, FIXTURE_ROOT / "waterfall", config)
    assert not report_before.ok

    stats = repair(store, FIXTURE_ROOT / "waterfall", config)
    assert stats.ghosts_removed >= 1
    assert not stats.errors

    report_after = reconcile(store, FIXTURE_ROOT / "waterfall", config)
    assert report_after.ok


def test_repair_ingests_missing_entity() -> None:
    from cataforge.kg._quads import quads_for_subject
    from cataforge.kg.ingest.iri import entity_iri
    from cataforge.kg.reconcile import reconcile
    from cataforge.kg.repair import repair

    handle, config = _make_populated_store()
    store = handle.raw

    iri = entity_iri("F-001", config.base_namespace)
    for q in quads_for_subject(store, iri):
        store.remove(q)

    report_before = reconcile(store, FIXTURE_ROOT / "waterfall", config)
    assert not report_before.ok

    stats = repair(store, FIXTURE_ROOT / "waterfall", config)
    assert stats.missing_ingested >= 1
    assert not stats.errors

    report_after = reconcile(store, FIXTURE_ROOT / "waterfall", config)
    assert report_after.ok


def test_repair_dry_run_no_mutation() -> None:
    from cataforge.kg._quads import quads_for_subject
    from cataforge.kg.ingest.iri import entity_iri
    from cataforge.kg.reconcile import reconcile
    from cataforge.kg.repair import repair

    handle, config = _make_populated_store()
    store = handle.raw

    iri = entity_iri("F-001", config.base_namespace)
    for q in quads_for_subject(store, iri):
        store.remove(q)

    stats = repair(store, FIXTURE_ROOT / "waterfall", config, dry_run=True)
    assert stats.missing_ingested > 0

    report = reconcile(store, FIXTURE_ROOT / "waterfall", config)
    assert not report.ok


def test_repair_idempotent() -> None:
    from cataforge.kg._quads import quads_for_subject
    from cataforge.kg.ingest.iri import entity_iri
    from cataforge.kg.repair import repair

    handle, config = _make_populated_store()
    store = handle.raw

    iri = entity_iri("F-001", config.base_namespace)
    for q in quads_for_subject(store, iri):
        store.remove(q)

    repair(store, FIXTURE_ROOT / "waterfall", config)

    stats2 = repair(store, FIXTURE_ROOT / "waterfall", config)
    assert stats2.ghosts_removed == 0
    assert stats2.missing_ingested == 0
