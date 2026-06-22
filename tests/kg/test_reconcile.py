"""`cataforge kg drift-check` unit + CLI smoke tests.

Sub-PR 6 — closes the loop on Alpha exit condition 2 (doctor gate
ERROR-enforced for one full reconcile cycle): without a working
reconcile we cannot certify the cycle happened.
"""

from __future__ import annotations

import gc
import json
from pathlib import Path

from click.testing import CliRunner

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _setup_project_with_kg(tmp_path: Path, variant: str = "waterfall") -> Path:
    """Copy a fixture variant into tmp_path and run the ingest codemod."""
    import shutil

    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.domain.kg.ingest import run_migration

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
    from cataforge.interface.cli.main import _register_commands, cli

    _register_commands()
    return cli


def test_reconcile_clean_fixture_is_ok(tmp_path: Path) -> None:
    """Freshly ingested fixture must reconcile with zero divergence."""
    from cataforge.domain.kg import KGConfig, KnowledgeGraphStore
    from cataforge.domain.kg.reconcile import reconcile

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
    from cataforge.domain.kg import KGConfig, KnowledgeGraphStore
    from cataforge.domain.kg.reconcile import reconcile

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
    from cataforge.domain.kg import KGConfig, KnowledgeGraphStore
    from cataforge.domain.kg.reconcile import reconcile

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
    from cataforge.domain.kg import KGConfig, KnowledgeGraphStore
    from cataforge.domain.kg.reconcile import reconcile

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


def test_reconcile_detects_orphan_target_edge(tmp_path: Path) -> None:
    """A traceability edge whose target entity node no longer exists surfaces as
    an orphan relation. The entity_id-keyed relation diff inner-joins the
    object's cf:entity_id and silently drops such an edge, so reconcile would
    otherwise report divergence=0 on a broken reference."""
    import pyoxigraph as ox

    from cataforge.domain.kg import KGConfig, KnowledgeGraphStore
    from cataforge.domain.kg._quads import _slot_iri
    from cataforge.domain.kg._sparql_utils import cf_namespace
    from cataforge.domain.kg.ingest.iri import entity_iri
    from cataforge.domain.kg.reconcile import reconcile

    project_root = _setup_project_with_kg(tmp_path)
    config = KGConfig(
        store_backend="oxigraph",
        db_path=project_root / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )
    ns = cf_namespace(config)
    with KnowledgeGraphStore.connect(config) as handle:
        handle.raw.add(
            ox.Quad(
                ox.NamedNode(entity_iri("M-001", config.base_namespace)),
                ox.NamedNode(_slot_iri("cf:implements", ns)),
                ox.NamedNode(entity_iri("F-404", config.base_namespace)),
            )
        )
        report = reconcile(handle.raw, project_root, config)

    assert not report.ok
    arch = report.per_doc_type["arch"]
    assert ("M-001", "cf:implements", "F-404") in arch.orphan_relations
    # The dangling-target edge must not also masquerade as missing/ghost.
    assert ("M-001", "cf:implements", "F-404") not in arch.ghost_relations
    assert ("M-001", "cf:implements", "F-404") not in arch.missing_relations


def test_reconcile_cross_doc_relation_attributed_by_subject_home(tmp_path: Path) -> None:
    """A relation whose subject is defined in one doc but *declared* in another
    must reconcile cleanly. Here arch holds 'F-001 … 映射功能: prd#§2.F-002', so the
    edge's subject (F-001) lives in prd while the xref sits in arch. The KG keys
    the edge by F-001's `cf:source_doc` (prd); the FS side must attribute it to
    prd too, not to the arch doc that merely declares it.
    """
    import gc

    from cataforge.domain.kg import KGConfig, KnowledgeGraphStore, init_store
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.domain.kg.ingest import run_migration
    from cataforge.domain.kg.reconcile import reconcile

    project_root = _setup_project_with_kg(tmp_path)
    arch = project_root / "docs" / "arch" / "arch-vertical-slice.md"
    arch.write_text(
        arch.read_text(encoding="utf-8")
        + "\n\n## §3 跨域引用\n\nF-001 复用登出能力\n\n- 映射功能: prd#§2.F-002\n",
        encoding="utf-8",
    )

    config = KGConfig(
        store_backend="oxigraph",
        db_path=project_root / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )
    handle = init_store(config, force=True)
    _stats, _entities, relations = run_migration(handle.raw, project_root, config)
    del handle
    gc.collect()
    invalidate_cache()

    # Non-vacuous: the cross-doc edge F-001 → F-002 was actually extracted.
    assert any(
        r.subject_entity_id == "F-001" and r.object_entity_id == "F-002" for r in relations
    ), [(r.subject_entity_id, r.predicate_curie, r.object_entity_id) for r in relations]

    with KnowledgeGraphStore.connect(config) as handle:
        report = reconcile(handle.raw, project_root, config)

    assert report.ok, report.to_dict()


def test_reconcile_agile_variant_is_clean(tmp_path: Path) -> None:
    """The agile fixture (same content, different process_model) reconciles
    just as cleanly as waterfall.
    """
    from cataforge.domain.kg import KGConfig, KnowledgeGraphStore
    from cataforge.domain.kg.reconcile import reconcile

    project_root = _setup_project_with_kg(tmp_path, variant="agile")
    config = KGConfig(
        store_backend="oxigraph",
        db_path=project_root / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )
    with KnowledgeGraphStore.connect(config) as handle:
        report = reconcile(handle.raw, project_root, config)

    assert report.ok, report.to_dict()


def _graph_project(tmp_path: Path) -> tuple[Path, object]:
    """A fresh graph-mode project with an empty store; returns (root, config)."""
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg._dispatch import invalidate_cache

    proj = tmp_path / "g"
    (proj / ".cataforge").mkdir(parents=True)
    (proj / "docs").mkdir()
    config = KGConfig(
        store_backend="oxigraph",
        db_path=proj / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch"},
    )
    handle = init_store(config, force=True)
    handle.raw.flush()
    handle.close()
    del handle
    gc.collect()
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"mode": "graph", "kg_active_doc_types": ["prd", "arch"]}}),
        encoding="utf-8",
    )
    invalidate_cache()
    gc.collect()
    return proj, config


def test_reconcile_graph_orphan_entity_cards_have_no_phantom_divergence(tmp_path: Path) -> None:
    """Entities authored straight into the graph (no Document) export as
    per-entity cards. Re-scanning those cards must NOT surface phantom
    missing/ghost — the symmetric diff spans Document-backed content only."""
    from cataforge.application.context import write as cw
    from cataforge.domain.kg import KnowledgeGraphStore
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.domain.kg.reconcile import reconcile

    proj, config = _graph_project(tmp_path)
    cw.author_entity(str(proj), entity_id="F-001", class_name="Feature", title="登录")
    gc.collect()
    cw.author_entity(str(proj), entity_id="F-002", class_name="Feature", title="登出")
    gc.collect()
    cw.author_entity(
        str(proj),
        entity_id="M-001",
        class_name="Module",
        title="认证模块",
        relations=[("implements", "F-001")],
    )
    gc.collect()
    cw.finalize(str(proj), None)
    gc.collect()
    invalidate_cache()
    gc.collect()

    with KnowledgeGraphStore.connect(config) as handle:
        report = reconcile(handle.raw, proj, config)

    assert report.overall_divergence_count == 0, report.to_dict()
    assert report.ok is True


def test_reconcile_graph_whole_doc_roundtrip_is_clean(tmp_path: Path) -> None:
    """A whole document authored into the graph then exported reconciles with
    zero divergence (the Document round-trip is faithful)."""
    from cataforge.application.context import write as cw
    from cataforge.domain.kg import KnowledgeGraphStore
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.domain.kg.reconcile import reconcile

    proj, config = _graph_project(tmp_path)
    prd_md = (
        "---\nid: prd\ndoc_type: prd\nstatus: draft\n---\n\n"
        "# PRD\n\n## §2 功能列表\n\n"
        "### F-001 登录\n\n- **验收标准**:\n  - AC-001: 可登录\n\n"
        "### F-002 登出\n\n说明。\n"
    )
    arch_md = (
        "---\nid: arch\ndoc_type: arch\nstatus: draft\n---\n\n"
        "# ARCH\n\n## §2 模块\n\n"
        "### M-001 认证模块\n\n- 对应功能: prd#§2.F-001\n"
    )
    cw.author_document(str(proj), prd_md)
    gc.collect()
    cw.author_document(str(proj), arch_md)
    gc.collect()
    cw.finalize(str(proj), None)
    gc.collect()
    invalidate_cache()
    gc.collect()

    with KnowledgeGraphStore.connect(config) as handle:
        report = reconcile(handle.raw, proj, config)

    assert report.overall_divergence_count == 0, report.to_dict()
    assert report.ok is True


def test_reconcile_cli_clean_exits_zero_and_writes_report(tmp_path: Path) -> None:
    project_root = _setup_project_with_kg(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        _cli(),
        [
            "kg",
            "drift-check",
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
    from cataforge.domain.kg._config import BUSINESS_DOC_TYPES

    # No kg_active_doc_types in the fixture → CLI resolves the full default set.
    assert set(payload["active_doc_types"]) == set(BUSINESS_DOC_TYPES)
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
            "drift-check",
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
