"""ensure_store hydrates the KG store per context.mode, idempotently.

markdown — no graph backend, nothing to do.
graph    — the store is the working copy of the .nq snapshot SoT; restore the
           latest snapshot, or seed an empty store when none was authored yet.
"""

from __future__ import annotations

import gc
import json
import shutil
from pathlib import Path

import pytest

from cataforge.application.context import write as cw
from cataforge.domain.kg import KGConfig, KnowledgeGraph
from cataforge.domain.kg._dispatch import invalidate_cache

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"

_GRAPH_DOC = (
    "---\nid: prd\ndoc_type: prd\nauthor: product-manager\nstatus: draft\ndeps: []\n---\n"
    "# PRD\n\n引言段落。\n\n"
    "## §1 功能\n\n### F-001 用户登录\n\n用户可用邮箱登录。\n\n"
)


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    gc.collect()
    yield
    invalidate_cache()
    gc.collect()


def _project(tmp_path: Path, *, mode: str, with_fixture_docs: bool = False) -> Path:
    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    if with_fixture_docs:
        shutil.copytree(FIXTURE_ROOT / "waterfall" / "docs", proj / "docs")
    else:
        (proj / "docs").mkdir()
    ctx = {"mode": mode, "kg_active_doc_types": ["prd", "arch", "test-report"]}
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": ctx}), encoding="utf-8"
    )
    invalidate_cache()
    gc.collect()
    return proj


def _store_dir(proj: Path) -> Path:
    return proj / ".cataforge" / "kg" / "store"


def _store_entity_ids(proj: Path) -> set[str]:
    cfg = KGConfig(store_backend="oxigraph", db_path=_store_dir(proj))
    with KnowledgeGraph.connect(cfg, read_only=True) as kg:
        return kg.query.entity_ids()


def test_ensure_store_markdown_is_noop(tmp_path: Path) -> None:
    proj = _project(tmp_path, mode="markdown")
    result = cw.ensure_store(str(proj))
    gc.collect()
    assert result.action == "noop"
    assert not _store_dir(proj).exists()


def test_ensure_store_graph_restores_latest_snapshot(tmp_path: Path) -> None:
    proj = _project(tmp_path, mode="graph")
    cw.ensure_store(str(proj))  # bootstrap seeds an empty store
    gc.collect()
    cw.author_document(str(proj), _GRAPH_DOC, source_path="docs/prd/prd.md")
    gc.collect()
    cw.finalize(str(proj))  # graph finalize auto-snapshots
    gc.collect()
    before = _store_entity_ids(proj)
    assert "F-001" in before
    gc.collect()

    shutil.rmtree(_store_dir(proj))  # fresh clone: store gone, snapshot remains
    gc.collect()

    result = cw.ensure_store(str(proj))
    gc.collect()

    assert result.action == "restored"
    assert _store_entity_ids(proj) == before


def test_ensure_store_graph_no_snapshot_seeds_empty(tmp_path: Path) -> None:
    proj = _project(tmp_path, mode="graph")
    result = cw.ensure_store(str(proj))
    gc.collect()
    assert result.action == "initialized"
    assert _store_dir(proj).exists()


def test_ensure_store_idempotent_when_store_present(tmp_path: Path) -> None:
    proj = _project(tmp_path, mode="graph")
    cw.ensure_store(str(proj))  # seeds an empty store
    gc.collect()
    result = cw.ensure_store(str(proj))  # store already present
    gc.collect()
    assert result.action == "noop"
