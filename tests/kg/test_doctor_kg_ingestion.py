"""Doctor `kg_ingestion_completeness` gate tests.

Per Task 7 §7.1 sub-PR 5 (and the explicit user decision in
[README §User decisions]), the gate ships at ERROR severity without a
WARN-to-ERROR promotion period: missing entities contribute to the
doctor exit code from the moment cutover lands.
"""
from __future__ import annotations

import gc
import json
from dataclasses import dataclass
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"

@dataclass
class FakePaths:
    root: Path

    @property
    def framework_json(self) -> Path:
        return self.root / ".cataforge" / "framework.json"

@dataclass
class FakeConfig:
    paths: FakePaths

def _setup_project_with_kg(tmp_path: Path) -> Path:
    """Copy the waterfall fixture into tmp_path and ingest into KG."""
    import shutil

    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    source = FIXTURE_ROOT / "waterfall"
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
    return project_root

def test_gate_passes_when_fs_matches_kg(tmp_path, capsys) -> None:
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0, out
    assert "OK" in out

def test_gate_fails_when_kg_missing_fs_entity(tmp_path, capsys) -> None:
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    # Append a brand-new entity to the PRD so FS has it but KG does not.
    prd = project_root / "docs" / "prd" / "prd-vertical-slice.md"
    prd.write_text(
        prd.read_text(encoding="utf-8") + "\n\n### §2.3 F-999 New feature\n",
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 1
    assert "FAIL" in out
    assert "F-999" in out

def test_gate_warns_but_does_not_fail_on_stale_only(tmp_path, capsys) -> None:
    """A KG entity present but no longer on disk surfaces as WARN; the
    gate stays green because the active read path still resolves —
    stale entities are cleanup debt, not correctness hazards.
    """
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = _setup_project_with_kg(tmp_path)
    # Remove TC-002 from the test-report so KG has it but FS does not.
    # Use a non-entity-id replacement so FS sees fewer entities, not new ones.
    tc_file = project_root / "docs" / "test-report" / "test-report-vertical-slice.md"
    content = tc_file.read_text(encoding="utf-8")
    new_content = content.replace("TC-002", "REMOVED")
    tc_file.write_text(new_content, encoding="utf-8")

    cfg = FakeConfig(paths=FakePaths(root=project_root))
    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    # FS = {F-001, F-002, AC-001, AC-002, M-001, M-002, TC-001}
    # KG = {... + TC-002}
    # missing: ∅ → no FAIL
    # stale:   {TC-002} → WARN, but failures stays 0
    assert failures == 0, out
    assert "TC-002" in out, "stale TC-002 must appear in WARN"
    assert "WARN" in out

def test_gate_skips_when_no_store(tmp_path, capsys) -> None:
    """No `.cataforge/kg/store/` present → gate returns 0 (skip).

    Downstream projects that have not opted into KG cutover are not
    blocked by this gate.
    """
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = tmp_path / "proj"
    (project_root / "docs").mkdir(parents=True)
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0
    assert "skipping" in out

def test_gate_skips_when_no_active_doc_types(tmp_path, capsys) -> None:
    """No `kg.kg_active_doc_types` in framework.json AND no built-in
    default for an empty project — skip cleanly.
    """
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_ingestion_completeness

    project_root = tmp_path / "proj"
    (project_root / ".cataforge" / "kg" / "store").mkdir(parents=True)
    (project_root / "docs").mkdir(parents=True)
    (project_root / ".cataforge" / "framework.json").write_text(
        json.dumps({"kg": {"kg_active_doc_types": []}}),
        encoding="utf-8",
    )
    cfg = FakeConfig(paths=FakePaths(root=project_root))

    failures = check_kg_ingestion_completeness(cfg)
    out = capsys.readouterr().out

    assert failures == 0
    assert "skipping" in out
