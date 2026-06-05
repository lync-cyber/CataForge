"""KG-first authoring lifecycle (Phase 3): write / validate / finalize / ingest / reconcile."""

from __future__ import annotations

import gc
import json
import shutil
from pathlib import Path

import pytest

from cataforge.application.context import write as cw
from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
from cataforge.domain.kg._dispatch import invalidate_cache
from cataforge.domain.kg._errors import KGValidationError

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    gc.collect()
    yield
    invalidate_cache()
    gc.collect()


def _project(tmp_path: Path, *, with_fixture_docs: bool = False) -> Path:
    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    if with_fixture_docs:
        shutil.copytree(FIXTURE_ROOT / "waterfall" / "docs", proj / "docs")
    else:
        (proj / "docs").mkdir()
    cfg = KGConfig(
        store_backend="oxigraph",
        db_path=proj / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test-report"},
    )
    handle = init_store(cfg, force=True)
    handle.raw.flush()
    handle.close()
    ctx = {"strategy": "kg-first", "kg_active_doc_types": ["prd", "arch", "test-report"]}
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": ctx}), encoding="utf-8"
    )
    invalidate_cache()
    gc.collect()
    return proj


def _connect(proj: Path) -> KGConfig:
    return KGConfig(
        store_backend="oxigraph",
        db_path=proj / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test-report"},
    )


# ---- authorized write -------------------------------------------------------


def test_author_valid_entity_persists(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    iri = cw.author_entity(str(proj), entity_id="F-001", class_name="Feature", title="用户登录")
    assert iri.endswith("F-001")
    gc.collect()
    with KnowledgeGraph.connect(_connect(proj)) as kg:
        assert kg.query.exists("F-001")
    gc.collect()


def test_author_wrong_class_rejected(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with pytest.raises(KGValidationError, match="maps to Feature"):
        cw.author_entity(str(proj), entity_id="F-001", class_name="Module", title="x")
    gc.collect()
    with KnowledgeGraph.connect(_connect(proj)) as kg:
        assert not kg.query.exists("F-001")  # nothing persisted
    gc.collect()


def test_author_unknown_prefix_rejected(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with pytest.raises(KGValidationError, match="no schema-known prefix"):
        cw.author_entity(str(proj), entity_id="ZZZ-001", class_name="Feature", title="x")
    gc.collect()


def test_write_narrative_creates_section(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.write_narrative(str(proj), doc_id="arch", anchor="§1 概览", narrative="架构概览文本")
    gc.collect()
    cfg = _connect(proj)
    ns = cfg.ontology_namespace.rstrip("/") + "/"
    with KnowledgeGraph.connect(cfg) as kg:
        rows = list(
            kg.store.query(
                f"PREFIX cf: <{ns}> SELECT ?b WHERE {{ "
                '?s a cf:Section ; cf:source_doc "arch" ; cf:narrative_body ?b }'
            )
        )
        assert any("架构概览" in str(r["b"].value) for r in rows)
    gc.collect()


# ---- finalize (KG -> md export of authored content) -------------------------


def test_finalize_exports_authored_entity(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.author_entity(str(proj), entity_id="F-001", class_name="Feature", title="用户登录")
    gc.collect()
    result = cw.finalize(str(proj), output_dir=str(tmp_path / "out"))
    gc.collect()
    assert not result.errors
    assert any("F-001" in str(rec.output_path) for rec in result.file_records)


def test_finalize_seeds_empty_graph_from_markdown(tmp_path: Path) -> None:
    """Markdown-first authoring leaves the graph empty; finalize must seed it
    (md→KG) so the reconcile guard is clean, without re-exporting over the
    authored Markdown (a lossy round-trip). ``_project`` initializes the store
    without ingesting, so the graph starts empty by construction."""
    proj = _project(tmp_path, with_fixture_docs=True)

    result = cw.finalize(str(proj))
    gc.collect()
    assert not result.errors
    # md-first 定稿 seeds the graph but does not re-export — the authored
    # Markdown is canonical and stays untouched.
    assert not result.file_records

    # Reconcile is clean only because the graph was seeded from the markdown;
    # an unseeded (empty) graph would report every authored doc as drift.
    report = cw.reconcile_check(str(proj))
    gc.collect()
    assert report.ok, report.to_dict()


# ---- ingest + reconcile (md -> KG round-trip on aggregated docs) ------------


def test_ingest_then_reconcile_clean(tmp_path: Path) -> None:
    proj = _project(tmp_path, with_fixture_docs=True)
    stats = cw.ingest(str(proj))
    gc.collect()
    assert stats.write_stats.entities_written > 0
    report = cw.reconcile_check(str(proj))
    gc.collect()
    assert report.ok, report.to_dict()


# ---- CLI facade -------------------------------------------------------------


def test_context_cli_registers_lifecycle_commands() -> None:
    from click.testing import CliRunner

    from cataforge.interface.cli.main import _register_commands, cli

    _register_commands()
    result = CliRunner().invoke(cli, ["context", "--help"])
    assert result.exit_code == 0
    for sub in ("read", "write", "write-narrative", "finalize", "ingest", "reconcile"):
        assert sub in result.output, f"missing context subcommand: {sub}"
