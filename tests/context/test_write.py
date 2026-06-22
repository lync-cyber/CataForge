"""KG-first authoring lifecycle (Phase 3): write / validate / finalize / ingest / reconcile."""

from __future__ import annotations

import gc
import json
import shutil
from pathlib import Path

import pytest

from cataforge.application.context import write as cw
from cataforge.application.context.write import CompileResult, DocIndexResult
from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
from cataforge.domain.kg._dispatch import invalidate_cache
from cataforge.domain.kg._errors import KGEntityNotFoundError, KGValidationError

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    gc.collect()
    yield
    invalidate_cache()
    gc.collect()


def _project(tmp_path: Path, *, with_fixture_docs: bool = False, mode: str | None = None) -> Path:
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
    ctx: dict[str, object] = {
        "mode": "hybrid",
        "kg_active_doc_types": ["prd", "arch", "test-report"],
    }
    if mode is not None:
        ctx["mode"] = mode
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
    proj = _project(tmp_path, mode="graph")
    iri = cw.author_entity(str(proj), entity_id="F-001", class_name="Feature", title="用户登录")
    assert iri.endswith("F-001")
    gc.collect()
    with KnowledgeGraph.connect(_connect(proj)) as kg:
        assert kg.query.exists("F-001")
    gc.collect()


def test_author_wrong_class_rejected(tmp_path: Path) -> None:
    proj = _project(tmp_path, mode="graph")
    with pytest.raises(KGValidationError, match="maps to Feature"):
        cw.author_entity(str(proj), entity_id="F-001", class_name="Module", title="x")
    gc.collect()
    with KnowledgeGraph.connect(_connect(proj)) as kg:
        assert not kg.query.exists("F-001")  # nothing persisted
    gc.collect()


def test_author_unknown_prefix_rejected(tmp_path: Path) -> None:
    proj = _project(tmp_path, mode="graph")
    with pytest.raises(KGValidationError, match="no schema-known prefix"):
        cw.author_entity(str(proj), entity_id="ZZZ-001", class_name="Feature", title="x")
    gc.collect()


def test_write_narrative_creates_section(tmp_path: Path) -> None:
    proj = _project(tmp_path, mode="graph")
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
    # Graph authoring: the graph is canonical, so 定稿 exports the md view.
    proj = _project(tmp_path, mode="graph")
    cw.author_entity(str(proj), entity_id="F-001", class_name="Feature", title="用户登录")
    gc.collect()
    result = cw.finalize(str(proj), output_dir=str(tmp_path / "out"))
    gc.collect()
    assert isinstance(result, CompileResult)
    assert not result.errors
    assert any("F-001" in str(rec.output_path) for rec in result.file_records)


def test_finalize_seeds_empty_graph_from_markdown(tmp_path: Path) -> None:
    """Markdown-first authoring leaves the graph empty; finalize must seed it
    (md→KG) so the reconcile guard is clean, without re-exporting over the
    authored Markdown (a lossy round-trip). ``_project`` initializes the store
    without ingesting, so the graph starts empty by construction."""
    proj = _project(tmp_path, with_fixture_docs=True)
    before = {p: p.read_text(encoding="utf-8") for p in (proj / "docs").rglob("*.md")}

    result = cw.finalize(str(proj))
    gc.collect()
    # md-first 定稿 reflects md → KG and rebuilds the index; it does not export
    # — the authored Markdown is canonical and stays untouched.
    assert isinstance(result, DocIndexResult)
    for path, text in before.items():
        assert path.read_text(encoding="utf-8") == text

    # Reconcile is clean only because the graph was seeded from the markdown;
    # an unseeded (empty) graph would report every authored doc as drift.
    report = cw.reconcile_check(str(proj))
    gc.collect()
    assert report.ok, report.to_dict()


def test_finalize_does_not_seed_empty_graph_under_graph_authoring(tmp_path: Path) -> None:
    """Under ``mode = "graph"`` an empty graph means nothing authored yet;
    finalize must not seed from the Markdown on disk."""
    proj = _project(tmp_path, with_fixture_docs=True)
    ctx = {
        "mode": "graph",
        "kg_active_doc_types": ["prd", "arch", "test-report"],
    }
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": ctx}), encoding="utf-8"
    )
    invalidate_cache()

    result = cw.finalize(str(proj))
    gc.collect()
    assert not result.errors
    assert not result.file_records
    assert result.discovered_count == 0

    # No seed happened — the graph stays empty.
    with KnowledgeGraph.connect(_connect(proj)) as kg:
        assert not kg.query.entity_ids()
        assert not kg.query.has_documents()
    gc.collect()


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
    for sub in (
        "read",
        "write",
        "write-narrative",
        "finalize",
        "ingest",
        "reconcile",
        "update",
        "delete",
    ):
        assert sub in result.output, f"missing context subcommand: {sub}"


# ---- update_entity (in-place slot merge, M2) --------------------------------


def test_update_entity_changes_slot_in_place(tmp_path: Path) -> None:
    proj = _project(tmp_path, mode="graph")
    cw.author_entity(
        str(proj),
        entity_id="F-001",
        class_name="Feature",
        title="登录",
        slots={"priority": "P0"},
    )
    gc.collect()

    result = cw.update_entity(str(proj), "F-001", slots={"priority": "P1"})
    assert result.changed is True
    assert result.slots_updated == ["priority"]
    gc.collect()

    cfg = _connect(proj)
    ns = cfg.ontology_namespace.rstrip("/") + "/"
    with KnowledgeGraph.connect(cfg) as kg:
        rows = list(
            kg.store.query(
                f'PREFIX cf: <{ns}> SELECT ?p WHERE {{ ?s cf:entity_id "F-001" ; cf:priority ?p }}'
            )
        )
        assert [str(r["p"].value) for r in rows] == ["P1"]
    gc.collect()


def test_update_entity_preserves_source_doc(tmp_path: Path) -> None:
    # An in-place slot edit must not relocate the entity's document membership.
    proj = _project(tmp_path, mode="graph")
    cw.author_entity(str(proj), entity_id="F-001", class_name="Feature", title="登录")
    gc.collect()
    cfg = _connect(proj)
    ns = cfg.ontology_namespace.rstrip("/") + "/"

    def _source_doc() -> list[str]:
        with KnowledgeGraph.connect(cfg) as kg:
            rows = list(
                kg.store.query(
                    f"PREFIX cf: <{ns}> "
                    'SELECT ?d WHERE { ?s cf:entity_id "F-001" ; cf:source_doc ?d }'
                )
            )
        gc.collect()
        return [str(r["d"].value) for r in rows]

    before = _source_doc()
    assert before, "authored entity should carry a source_doc"

    cw.update_entity(str(proj), "F-001", title="登录v2")
    gc.collect()

    assert _source_doc() == before


def test_update_entity_absent_raises(tmp_path: Path) -> None:
    proj = _project(tmp_path, mode="graph")
    with pytest.raises(KGEntityNotFoundError):
        cw.update_entity(str(proj), "F-404", title="x")
    gc.collect()


def test_update_rejected_in_hybrid_mode(tmp_path: Path) -> None:
    proj = _project(tmp_path, mode="hybrid")
    with pytest.raises(cw.ContextModeError, match="hybrid"):
        cw.update_entity(str(proj), "F-001", title="x")
    gc.collect()


# ---- delete_entity (M1) -----------------------------------------------------


def test_delete_entity_removes_node(tmp_path: Path) -> None:
    proj = _project(tmp_path, mode="graph")
    cw.author_entity(str(proj), entity_id="F-001", class_name="Feature", title="登录")
    gc.collect()

    result = cw.delete_entity(str(proj), "F-001")
    assert result.quads_removed > 0
    gc.collect()

    with KnowledgeGraph.connect(_connect(proj)) as kg:
        assert not kg.query.exists("F-001")
    gc.collect()


def test_delete_entity_absent_raises(tmp_path: Path) -> None:
    proj = _project(tmp_path, mode="graph")
    with pytest.raises(KGEntityNotFoundError):
        cw.delete_entity(str(proj), "F-404")
    gc.collect()


def test_delete_rejected_in_markdown_mode(tmp_path: Path) -> None:
    proj = _project(tmp_path, mode="markdown")
    with pytest.raises(cw.ContextModeError, match="markdown"):
        cw.delete_entity(str(proj), "F-001")
    gc.collect()
