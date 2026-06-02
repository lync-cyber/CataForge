"""`cataforge kg compare-read` audit tests.

Sub-PR 6 — diagnostic, not gating; alarms surface but the CLI always
exits 0. Reproducibility is anchored by the `--seed` flag.
Content-hash compare semantics (see compare_read.py docstring).
"""

from __future__ import annotations

import gc
import json
from pathlib import Path

from click.testing import CliRunner

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _setup_project_with_kg(tmp_path: Path) -> Path:
    import shutil

    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg._dispatch import invalidate_cache
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
    invalidate_cache()
    return project_root


def _cli():
    from cataforge.interface.cli.main import _register_commands, cli

    _register_commands()
    return cli


def test_compare_read_clean_fixture_no_alarms(tmp_path: Path) -> None:
    """Freshly ingested fixture must audit clean: every sampled entity's
    FS-recomputed content_hash equals the `cf:content_hash` literal in KG.
    """
    from cataforge.domain.kg import KGConfig, KnowledgeGraph
    from cataforge.domain.kg.compare_read import compare_read

    project_root = _setup_project_with_kg(tmp_path)
    config = KGConfig(
        store_backend="oxigraph",
        db_path=project_root / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )
    with KnowledgeGraph.connect(config) as kg:
        report = compare_read(
            kg,
            project_root,
            doc_types={"prd", "arch", "test"},
            sample_size=100,  # > population → audit every entity
            seed=42,
        )

    assert report.sampled_count == 9  # F×2 + AC×2 + M×2 + TC×2 + TS×1
    assert report.alarms == [], [a.to_dict() for a in report.alarms]


def test_compare_read_flags_mutated_section_body(tmp_path: Path) -> None:
    """Mutating the body of an entity's section after ingest must surface
    as a content_hash mismatch alarm.
    """
    from cataforge.domain.kg import KGConfig, KnowledgeGraph
    from cataforge.domain.kg.compare_read import compare_read

    project_root = _setup_project_with_kg(tmp_path)

    tc_file = project_root / "docs" / "test-report" / "test-report-vertical-slice.md"
    text = tc_file.read_text(encoding="utf-8")
    rewritten = text.replace(
        "- 验证: prd#§2.AC-001",
        "- 验证: prd#§2.AC-001\n- (body mutated post-ingest)",
    )
    assert rewritten != text, "fixture content shifted; update the replace target"
    tc_file.write_text(rewritten, encoding="utf-8")

    config = KGConfig(
        store_backend="oxigraph",
        db_path=project_root / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )
    with KnowledgeGraph.connect(config) as kg:
        report = compare_read(
            kg,
            project_root,
            doc_types={"test"},
            sample_size=100,
            seed=42,
        )

    alarm_map = {a.entity_id: a for a in report.alarms}
    assert "TC-001" in alarm_map
    assert alarm_map["TC-001"].reason == "content-hash-mismatch"
    assert alarm_map["TC-001"].kg_content_hash is not None
    assert alarm_map["TC-001"].kg_content_hash != alarm_map["TC-001"].fs_content_hash


def test_compare_read_flags_kg_missing_entity(tmp_path: Path) -> None:
    """A new entity in FS that hasn't been re-ingested into KG surfaces as
    `kg-missing-entity` alarm."""
    from cataforge.domain.kg import KGConfig, KnowledgeGraph
    from cataforge.domain.kg.compare_read import compare_read

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
    with KnowledgeGraph.connect(config) as kg:
        report = compare_read(
            kg,
            project_root,
            doc_types={"prd"},
            sample_size=100,
            seed=42,
        )

    alarm_map = {a.entity_id: a for a in report.alarms}
    assert "F-999" in alarm_map
    assert alarm_map["F-999"].reason == "kg-missing-entity"


def test_compare_read_seed_is_reproducible(tmp_path: Path) -> None:
    from cataforge.domain.kg import KGConfig, KnowledgeGraph
    from cataforge.domain.kg.compare_read import compare_read

    project_root = _setup_project_with_kg(tmp_path)
    config = KGConfig(
        store_backend="oxigraph",
        db_path=project_root / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )
    with KnowledgeGraph.connect(config) as kg:
        r1 = compare_read(
            kg,
            project_root,
            doc_types={"prd", "arch", "test"},
            sample_size=3,
            seed=7,
        )
        r2 = compare_read(
            kg,
            project_root,
            doc_types={"prd", "arch", "test"},
            sample_size=3,
            seed=7,
        )

    assert r1.per_doc_type_counts == r2.per_doc_type_counts
    assert r1.sampled_count == r2.sampled_count


def test_compare_read_cli_exits_zero_even_on_alarms(tmp_path: Path) -> None:
    """Per task-7 §7.5, compare-read is diagnostic — alarms never set
    a non-zero exit code.
    """
    project_root = _setup_project_with_kg(tmp_path)
    tc_file = project_root / "docs" / "test-report" / "test-report-vertical-slice.md"
    text = tc_file.read_text(encoding="utf-8")
    rewritten = text.replace(
        "- 验证: prd#§2.AC-001",
        "- 验证: prd#§2.AC-001\n- (body mutated post-ingest)",
    )
    tc_file.write_text(rewritten, encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        _cli(),
        [
            "kg",
            "compare-read",
            "--project-root",
            str(project_root),
            "--db-path",
            str(project_root / ".cataforge" / "kg" / "store"),
            "--doc-type",
            "test",
            "--sample-size",
            "100",
            "--seed",
            "42",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["sampled_count"] >= 1
    assert any(a["entity_id"] == "TC-001" for a in payload["alarms"])
