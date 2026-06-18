"""finalize routes by authoring mode: the canonical side drives 定稿.

Under ``authoring = "md"`` the Markdown is canonical, so finalize reflects it
into the graph (md → KG) and never re-exports over the authored files. Under
``authoring = "graph"`` the graph is canonical, so finalize exports the
Markdown view and the export round-trip stays drift-free.
"""

from __future__ import annotations

import gc
import json
import shutil
from pathlib import Path

import pytest

from cataforge.application.context import write as cw
from cataforge.application.context.write import CompileResult, DocIndexResult
from cataforge.domain.kg import KGConfig, init_store
from cataforge.domain.kg._dispatch import invalidate_cache

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    gc.collect()
    yield
    invalidate_cache()
    gc.collect()


def _project(tmp_path: Path, *, authoring: str, with_fixture_docs: bool = False) -> Path:
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
    ctx = {
        "strategy": "kg-first",
        "authoring": authoring,
        "kg_active_doc_types": ["prd", "arch", "test-report"],
    }
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": ctx}), encoding="utf-8"
    )
    invalidate_cache()
    gc.collect()
    return proj


_GRAPH_DOC = (
    "---\nid: prd\ndoc_type: prd\nauthor: product-manager\nstatus: draft\ndeps: []\n---\n"
    "# PRD\n\n引言段落。\n\n"
    "## §1 功能\n\n### F-001 用户登录\n\n用户可用邮箱登录。\n\n"
    "## §2 说明\n\n补充说明文本。\n"
)


# ---- BUG-1: md authoring — finalize must not overwrite human-edited md -------


def test_finalize_md_preserves_human_edits_on_nonempty_graph(tmp_path: Path) -> None:
    """The core data-loss regression: edit the Markdown, then finalize over a
    non-empty graph — the hand edit must survive byte-for-byte."""
    proj = _project(tmp_path, authoring="md", with_fixture_docs=True)
    cw.ingest(str(proj))  # graph is now non-empty
    gc.collect()

    target = next((proj / "docs" / "arch").rglob("*.md"))
    edited = target.read_text(encoding="utf-8") + "\n\n## 99. 人工补充\n\n手写内容必须留存。\n"
    target.write_text(edited, encoding="utf-8")

    cw.finalize(str(proj))
    gc.collect()

    assert target.read_text(encoding="utf-8") == edited


def test_finalize_md_returns_index_result_and_reconciles_clean(tmp_path: Path) -> None:
    """md 定稿 is a md → KG reflect + index rebuild (a DocIndexResult), not an
    export; the graph absorbs the Markdown so reconcile is clean."""
    proj = _project(tmp_path, authoring="md", with_fixture_docs=True)
    cw.ingest(str(proj))
    gc.collect()

    result = cw.finalize(str(proj))
    gc.collect()

    assert isinstance(result, DocIndexResult)
    report = cw.reconcile_check(str(proj))
    gc.collect()
    assert report.ok, report.to_dict()


def test_finalize_md_empty_graph_seeds_without_re_export(tmp_path: Path) -> None:
    """md-first authoring leaves the graph empty until 定稿 seeds it (md → KG);
    the authored Markdown is canonical and is not rewritten."""
    proj = _project(tmp_path, authoring="md", with_fixture_docs=True)
    before = {p: p.read_text(encoding="utf-8") for p in (proj / "docs").rglob("*.md")}

    result = cw.finalize(str(proj))
    gc.collect()

    assert isinstance(result, DocIndexResult)
    for path, text in before.items():
        assert path.read_text(encoding="utf-8") == text  # nothing re-exported
    report = cw.reconcile_check(str(proj))
    gc.collect()
    assert report.ok, report.to_dict()


# ---- graph authoring — finalize exports; round-trip stays drift-free ---------


def test_finalize_graph_exports_and_reconciles_clean(tmp_path: Path) -> None:
    proj = _project(tmp_path, authoring="graph")
    cw.author_document(str(proj), _GRAPH_DOC, source_path="docs/prd/prd.md")
    gc.collect()

    result = cw.finalize(str(proj))
    gc.collect()

    assert isinstance(result, CompileResult)
    assert result.file_records
    report = cw.reconcile_check(str(proj))
    gc.collect()
    assert report.ok, report.to_dict()


def test_finalize_graph_export_is_byte_stable_across_runs(tmp_path: Path) -> None:
    """BUG-3 guard: the section/anchor round-trip is idempotent — re-finalize
    produces identical bytes, so reconcile never sees representational drift."""
    proj = _project(tmp_path, authoring="graph")
    cw.author_document(str(proj), _GRAPH_DOC, source_path="docs/prd/prd.md")
    gc.collect()

    out = proj / "docs" / "prd" / "prd.md"
    cw.finalize(str(proj))
    gc.collect()
    first = out.read_text(encoding="utf-8")

    cw.finalize(str(proj))
    gc.collect()
    second = out.read_text(encoding="utf-8")

    assert first == second
    report = cw.reconcile_check(str(proj))
    gc.collect()
    assert report.ok, report.to_dict()
