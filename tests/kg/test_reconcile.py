"""`cataforge kg reconcile` unit + CLI smoke tests.

Sub-PR 6 — closes the loop on Alpha exit condition 2 (doctor gate
ERROR-enforced for one full reconcile cycle): without a working
reconcile we cannot certify the cycle happened.
"""
from __future__ import annotations

import gc
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from click.testing import CliRunner

pyoxigraph_installed = importlib.util.find_spec("pyoxigraph") is not None
linkml_runtime_installed = importlib.util.find_spec("linkml_runtime") is not None

pytestmark = pytest.mark.skipif(
    not (pyoxigraph_installed and linkml_runtime_installed),
    reason="kg extra not installed (pyoxigraph + linkml-runtime)",
)


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _setup_project_with_kg(tmp_path: Path, variant: str = "waterfall") -> Path:
    """Copy a fixture variant into tmp_path and run the ingest codemod."""
    import shutil

    from cataforge.kg import KGConfig, init_store
    from cataforge.kg._dispatch import invalidate_cache
    from cataforge.kg.ingest import run_migration

    source = FIXTURE_ROOT / variant
    project_root = tmp_path / "proj"
    shutil.copytree(source, project_root)

    db_path = project_root / ".cataforge" / "kg" / "store"
    config = KGConfig(
        store_backend="oxigraph",
        db_path=db_path,
        kg_active_doc_types={"prd", "arch", "test"},
    )
    handle = init_store(config, force=True)
    run_migration(handle.raw, project_root, config)
    del handle
    gc.collect()
    invalidate_cache()
    return project_root


def _cli():
    from cataforge.cli.main import _register_commands, cli

    _register_commands()
    return cli


def test_reconcile_clean_fixture_is_ok(tmp_path: Path) -> None:
    """Freshly ingested fixture must reconcile with zero divergence."""
    from cataforge.kg import KGConfig, KnowledgeGraphStore
    from cataforge.kg.reconcile import reconcile

    project_root = _setup_project_with_kg(tmp_path)
    config = KGConfig(
        store_backend="oxigraph",
        db_path=project_root / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )
    with KnowledgeGraphStore.connect(config) as handle:
        report = reconcile(handle.raw, project_root, config)

    assert report.ok, report.to_dict()
    assert report.overall_divergence_count == 0
    assert set(report.per_doc_type) == {"prd", "arch", "test"}
    for per in report.per_doc_type.values():
        assert per.missing_entities == []
        assert per.ghost_entities == []
        assert per.missing_relations == []
        assert per.ghost_relations == []


def test_reconcile_detects_fs_only_entity(tmp_path: Path) -> None:
    """Appending a new entity_id to a markdown source must surface as missing."""
    from cataforge.kg import KGConfig, KnowledgeGraphStore
    from cataforge.kg.reconcile import reconcile

    project_root = _setup_project_with_kg(tmp_path)
    prd = project_root / "docs" / "prd" / "prd-vertical-slice.md"
    prd.write_text(
        prd.read_text(encoding="utf-8") + "\n\n### §2.3 F-999 New feature\n",
        encoding="utf-8",
    )

    config = KGConfig(
        store_backend="oxigraph",
        db_path=project_root / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )
    with KnowledgeGraphStore.connect(config) as handle:
        report = reconcile(handle.raw, project_root, config)

    assert not report.ok
    prd_report = report.per_doc_type["prd"]
    assert "F-999" in prd_report.missing_entities
    assert prd_report.ghost_entities == []


def test_reconcile_detects_kg_only_entity(tmp_path: Path) -> None:
    """Removing an entity from filesystem must surface as ghost in KG."""
    from cataforge.kg import KGConfig, KnowledgeGraphStore
    from cataforge.kg.reconcile import reconcile

    project_root = _setup_project_with_kg(tmp_path)
    tc_file = project_root / "docs" / "test-report" / "test-report-vertical-slice.md"
    # Replace TC-002 occurrences with REMOVED so FS scan no longer finds it.
    content = tc_file.read_text(encoding="utf-8")
    tc_file.write_text(content.replace("TC-002", "REMOVED"), encoding="utf-8")

    config = KGConfig(
        store_backend="oxigraph",
        db_path=project_root / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )
    with KnowledgeGraphStore.connect(config) as handle:
        report = reconcile(handle.raw, project_root, config)

    assert not report.ok
    test_report = report.per_doc_type["test"]
    assert "TC-002" in test_report.ghost_entities


def test_reconcile_detects_missing_relation(tmp_path: Path) -> None:
    """Stripping the cross-reference but keeping the entity should leave the
    entity intact and surface a missing relation only.
    """
    from cataforge.kg import KGConfig, KnowledgeGraphStore
    from cataforge.kg.reconcile import reconcile

    project_root = _setup_project_with_kg(tmp_path)
    arch_file = project_root / "docs" / "arch" / "arch-vertical-slice.md"
    content = arch_file.read_text(encoding="utf-8")
    # Drop the `映射功能: prd#§2.F-001` line — M-001 still defined, but the
    # implements edge to F-001 disappears from FS.
    rewritten = content.replace("- 映射功能: prd#§2.F-001\n", "")
    arch_file.write_text(rewritten, encoding="utf-8")

    config = KGConfig(
        store_backend="oxigraph",
        db_path=project_root / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )
    with KnowledgeGraphStore.connect(config) as handle:
        report = reconcile(handle.raw, project_root, config)

    assert not report.ok
    arch = report.per_doc_type["arch"]
    assert arch.missing_entities == []
    assert ("M-001", "cf:implements", "F-001") in arch.ghost_relations


def test_reconcile_agile_variant_is_clean(tmp_path: Path) -> None:
    """The agile fixture (same content, different process_model) reconciles
    just as cleanly as waterfall.
    """
    from cataforge.kg import KGConfig, KnowledgeGraphStore
    from cataforge.kg.reconcile import reconcile

    project_root = _setup_project_with_kg(tmp_path, variant="agile")
    config = KGConfig(
        store_backend="oxigraph",
        db_path=project_root / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )
    with KnowledgeGraphStore.connect(config) as handle:
        report = reconcile(handle.raw, project_root, config)

    assert report.ok, report.to_dict()


def test_reconcile_cli_clean_exits_zero_and_writes_report(tmp_path: Path) -> None:
    project_root = _setup_project_with_kg(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        _cli(),
        [
            "kg",
            "reconcile",
            "--project-root",
            str(project_root),
            "--db-path",
            str(project_root / ".cataforge" / "kg" / "store"),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["overall_divergence_count"] == 0
    assert set(payload["active_doc_types"]) == {"prd", "arch", "test"}
    report_path = project_root / "docs" / ".kg-reconcile-report.json"
    assert report_path.is_file()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["ok"] is True


def test_reconcile_cli_drift_exits_nonzero(tmp_path: Path) -> None:
    project_root = _setup_project_with_kg(tmp_path)
    prd = project_root / "docs" / "prd" / "prd-vertical-slice.md"
    prd.write_text(
        prd.read_text(encoding="utf-8") + "\n\n### §2.3 F-999 New feature\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        _cli(),
        [
            "kg",
            "reconcile",
            "--project-root",
            str(project_root),
            "--db-path",
            str(project_root / ".cataforge" / "kg" / "store"),
        ],
    )
    assert result.exit_code != 0
    assert "DRIFT" in result.output
    assert "prd" in result.output
    report_path = project_root / "docs" / ".kg-reconcile-report.json"
    assert report_path.is_file()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["per_doc_type"]["prd"]["missing_entities"] == ["F-999"]
