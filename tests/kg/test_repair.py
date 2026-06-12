"""Tests for KG repair."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _make_populated_store(variant: str = "waterfall"):
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, FIXTURE_ROOT / variant, config)
    return handle, config


def _copy_fixture_and_populate(tmp_path: Path, variant: str = "waterfall"):
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    project_root = tmp_path / "proj"
    shutil.copytree(FIXTURE_ROOT / variant, project_root)
    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, project_root, config)
    return project_root, handle, config


def _ask_cf(store, config, body: str) -> bool:
    from cataforge.domain.kg._ask import ask

    ns = config.ontology_namespace.rstrip("/") + "/"
    return ask(store, f"PREFIX cf: <{ns}> ASK {{ {body} }}")


def _rename_prd_overview_heading(project_root: Path) -> None:
    prd = project_root / "docs" / "prd" / "prd-vertical-slice.md"
    prd.write_text(
        prd.read_text(encoding="utf-8").replace("## §1 概览", "## §1 总览"),
        encoding="utf-8",
    )


def test_repair_on_clean_store_is_noop() -> None:
    from cataforge.domain.kg.repair import repair

    handle, config = _make_populated_store()
    stats = repair(handle.raw, FIXTURE_ROOT / "waterfall", config)
    assert stats.ghosts_removed == 0
    assert stats.missing_ingested == 0
    assert not stats.errors


def test_repair_removes_ghost_entity() -> None:
    from cataforge.domain.kg._quads import build_entity_quads
    from cataforge.domain.kg.ingest.iri import entity_iri
    from cataforge.domain.kg.reconcile import reconcile
    from cataforge.domain.kg.repair import repair

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
    from cataforge.domain.kg._quads import quads_for_subject
    from cataforge.domain.kg.ingest.iri import entity_iri
    from cataforge.domain.kg.reconcile import reconcile
    from cataforge.domain.kg.repair import repair

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
    from cataforge.domain.kg._quads import quads_for_subject
    from cataforge.domain.kg.ingest.iri import entity_iri
    from cataforge.domain.kg.reconcile import reconcile
    from cataforge.domain.kg.repair import repair

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
    from cataforge.domain.kg._quads import quads_for_subject
    from cataforge.domain.kg.ingest.iri import entity_iri
    from cataforge.domain.kg.repair import repair

    handle, config = _make_populated_store()
    store = handle.raw

    iri = entity_iri("F-001", config.base_namespace)
    for q in quads_for_subject(store, iri):
        store.remove(q)

    repair(store, FIXTURE_ROOT / "waterfall", config)

    stats2 = repair(store, FIXTURE_ROOT / "waterfall", config)
    assert stats2.ghosts_removed == 0
    assert stats2.missing_ingested == 0


def test_repair_ghost_restored_when_reingest_fails(tmp_path) -> None:
    """Ghost quads are restored if reingest raises (C1 compensating rollback)."""
    from unittest.mock import patch

    from cataforge.domain.kg._quads import build_entity_quads, quads_for_subject
    from cataforge.domain.kg.ingest.iri import entity_iri
    from cataforge.domain.kg.repair import repair

    handle, config = _make_populated_store()
    store = handle.raw

    # Add a ghost (F-999 only in KG, not in source).
    project_iri = entity_iri("proj-waterfall-slice", config.base_namespace)
    ghost_quads = build_entity_quads(
        entity_id="F-999",
        class_name="Feature",
        title="Ghost",
        source_doc="prd",
        source_section="F-999 Ghost",
        content_hash="e" * 64,
        project_iri=project_iri,
        config=config,
    )
    for q in ghost_quads:
        store.add(q)

    # Remove F-001 so reingest is required (which we then mock to fail).
    f001_iri = entity_iri("F-001", config.base_namespace)
    for q in quads_for_subject(store, f001_iri):
        store.remove(q)

    ghost_iri = entity_iri("F-999", config.base_namespace)
    assert len(quads_for_subject(store, ghost_iri)) > 0

    with patch(
        "cataforge.domain.kg.repair._reingest_doc_type",
        side_effect=RuntimeError("boom"),
    ):
        stats = repair(store, FIXTURE_ROOT / "waterfall", config)

    assert any("reingest" in e for e in stats.errors), f"expected reingest error in {stats.errors}"
    restored = quads_for_subject(store, ghost_iri)
    assert len(restored) > 0, "ghost quads must be restored after reingest failure"


def test_repair_uses_framework_project_id(tmp_path) -> None:
    """repair() reads project_id from framework.json (C4 fix)."""
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration
    from cataforge.domain.kg.repair import repair

    project_root = tmp_path / "myproject"
    waterfall_root = FIXTURE_ROOT / "waterfall"
    import shutil

    shutil.copytree(waterfall_root, project_root)

    framework_json = project_root / ".cataforge" / "framework.json"
    data = json.loads(framework_json.read_text(encoding="utf-8"))
    data["kg"]["project_id"] = "proj-custom-123"
    framework_json.write_text(json.dumps(data), encoding="utf-8")

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, project_root, config)
    store = handle.raw

    from cataforge.domain.kg._quads import quads_for_subject
    from cataforge.domain.kg.ingest.iri import entity_iri as _entity_iri

    f001_iri = _entity_iri("F-001", config.base_namespace)
    for q in quads_for_subject(store, f001_iri):
        store.remove(q)

    stats = repair(store, project_root, config)
    assert stats.missing_ingested >= 1
    assert not stats.errors

    namespace = config.ontology_namespace.rstrip("/") + "/"
    import pyoxigraph as ox

    from cataforge.domain.kg._quads import _slot_iri

    subject = ox.NamedNode(f001_iri)
    btp_pred = ox.NamedNode(_slot_iri("cf:belongs_to_project", namespace))
    project_refs = [q.object.value for q in store.quads_for_pattern(subject, btp_pred, None, None)]
    expected_project_iri = _entity_iri("proj-custom-123", config.base_namespace)
    assert project_refs == [expected_project_iri], (
        f"Expected belongs_to_project={expected_project_iri!r}, got {project_refs}"
    )


def test_repair_removes_ghost_section_scoped_to_its_doc(tmp_path: Path) -> None:
    from cataforge.domain.kg.ingest.iri import section_iri
    from cataforge.domain.kg.reconcile import reconcile
    from cataforge.domain.kg.repair import repair

    project_root, handle, config = _copy_fixture_and_populate(tmp_path)
    store = handle.raw
    _rename_prd_overview_heading(project_root)

    report_before = reconcile(store, project_root, config)
    assert "§1 概览" in report_before.per_doc_type["prd"].ghost_sections
    assert "§1 总览" in report_before.per_doc_type["prd"].missing_sections

    stats = repair(store, project_root, config)
    assert stats.ghost_sections_removed >= 1
    assert stats.missing_sections_ingested >= 1
    assert not stats.errors

    old_iri = section_iri("prd", "§1 概览", config.base_namespace)
    assert not _ask_cf(store, config, f"<{old_iri}> ?p ?o")
    assert not _ask_cf(store, config, f"?d cf:has_section <{old_iri}>")
    assert _ask_cf(
        store, config, '?s a cf:Section ; cf:section_anchor "§1 总览" ; cf:source_doc "prd"'
    )
    assert _ask_cf(
        store, config, '?s a cf:Section ; cf:section_anchor "§1 概览" ; cf:source_doc "arch"'
    )

    assert reconcile(store, project_root, config).ok

    stats2 = repair(store, project_root, config)
    assert stats2.ghost_sections_removed == 0
    assert stats2.missing_sections_ingested == 0


def test_repair_ingests_missing_section_without_entity_drift(tmp_path: Path) -> None:
    from cataforge.domain.kg.reconcile import reconcile
    from cataforge.domain.kg.repair import repair

    project_root, handle, config = _copy_fixture_and_populate(tmp_path)
    store = handle.raw

    prd = project_root / "docs" / "prd" / "prd-vertical-slice.md"
    prd.write_text(
        prd.read_text(encoding="utf-8") + "\n\n## §3 非功能约束\n\n响应时间低于一秒。\n",
        encoding="utf-8",
    )

    report_before = reconcile(store, project_root, config)
    per = report_before.per_doc_type["prd"]
    assert per.missing_sections == ["§3 非功能约束"]
    assert per.missing_entities == []
    assert per.missing_relations == []

    stats = repair(store, project_root, config)
    assert stats.missing_sections_ingested >= 1
    assert not stats.errors
    assert reconcile(store, project_root, config).ok


def test_repair_dry_run_counts_sections_without_mutation(tmp_path: Path) -> None:
    from cataforge.domain.kg.reconcile import reconcile
    from cataforge.domain.kg.repair import repair

    project_root, handle, config = _copy_fixture_and_populate(tmp_path)
    store = handle.raw
    _rename_prd_overview_heading(project_root)

    stats = repair(store, project_root, config, dry_run=True)
    assert stats.ghost_sections_removed >= 1
    assert stats.missing_sections_ingested >= 1

    assert _ask_cf(
        store, config, '?s a cf:Section ; cf:section_anchor "§1 概览" ; cf:source_doc "prd"'
    )
    assert not reconcile(store, project_root, config).ok


def test_repair_cli_json_reports_section_stats(tmp_path: Path) -> None:
    import gc

    from click.testing import CliRunner

    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.domain.kg.ingest import run_migration
    from cataforge.interface.cli.main import _register_commands, cli

    project_root = tmp_path / "proj"
    shutil.copytree(FIXTURE_ROOT / "waterfall", project_root)
    db_path = project_root / ".cataforge" / "kg" / "store"
    config = KGConfig(store_backend="oxigraph", db_path=db_path)
    handle = init_store(config, force=True)
    run_migration(handle.raw, project_root, config)
    del handle
    gc.collect()
    invalidate_cache()

    _rename_prd_overview_heading(project_root)

    _register_commands()
    result = CliRunner().invoke(
        cli,
        [
            "kg",
            "repair",
            "--project-root",
            str(project_root),
            "--db-path",
            str(db_path),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ghost_sections_removed"] >= 1
    assert payload["missing_sections_ingested"] >= 1
    assert payload["errors"] == []
