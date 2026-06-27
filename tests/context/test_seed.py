"""Graph migration seeding — turn a config-flipped project into a live graph.

A legacy hybrid (or mode-less) project flipped to ``context.mode = graph`` keeps
its Markdown but starts with an empty store and no snapshot. ``seed_graph_from_docs``
ingests the Markdown and finalizes it so reconcile is zero, and is idempotent:
once a snapshot exists (or the graph is populated) it skips.
"""

from __future__ import annotations

import gc
import json
from pathlib import Path

import pytest

from cataforge.application.context.seed import seed_graph_from_docs
from cataforge.core.paths import KG_SNAPSHOTS_REL
from cataforge.domain.kg import KGConfig, init_store
from cataforge.domain.kg._dispatch import invalidate_cache

_KG = {"project_id": "p", "title": "T", "process_model": "waterfall"}
_PRD = (
    "---\nid: prd\ndoc_type: prd\nstatus: draft\n---\n"
    "# PRD\n\n引言。\n\n## 1. 功能\n\n### F-001 登录\n\n用户可登录。\n"
)


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    gc.collect()
    yield
    invalidate_cache()
    gc.collect()


def _migrated_project(tmp_path: Path, *, mode: str = "graph", with_docs: bool = True) -> Path:
    """A project as it looks just after a config-flip: mode set, Markdown on
    disk, an empty store, and no snapshot."""
    proj = tmp_path / "proj"
    (proj / ".cataforge").mkdir(parents=True)
    framework = {
        "context": {"mode": mode, "kg_active_doc_types": ["prd"]},
        "kg": _KG,
        "docs": {"doc_types": {"prd": "prd"}},
    }
    (proj / ".cataforge" / "framework.json").write_text(json.dumps(framework), encoding="utf-8")
    if with_docs:
        prd_dir = proj / "docs" / "prd"
        prd_dir.mkdir(parents=True)
        (prd_dir / "prd.md").write_text(_PRD, encoding="utf-8")
    else:
        (proj / "docs").mkdir()
    cfg = KGConfig(store_backend="oxigraph", db_path=proj / ".cataforge" / "kg" / "store")
    init_store(cfg, force=True).close()
    invalidate_cache()
    gc.collect()
    return proj


def test_seeds_empty_graph_from_docs(tmp_path: Path) -> None:
    from cataforge.application.context import write as cw

    proj = _migrated_project(tmp_path)
    result = seed_graph_from_docs(str(proj))
    gc.collect()

    assert result.action == "seeded", result.detail
    # the Markdown entity is now in the graph and reconcile is clean
    assert cw.reconcile_check(str(proj)).ok
    snaps = list((proj / KG_SNAPSHOTS_REL).glob("*.nq"))
    assert snaps, "finalize during seed must write a snapshot"


def test_idempotent_second_run_skips(tmp_path: Path) -> None:
    proj = _migrated_project(tmp_path)
    first = seed_graph_from_docs(str(proj))
    gc.collect()
    assert first.action == "seeded"

    second = seed_graph_from_docs(str(proj))
    gc.collect()
    assert second.action == "skipped"
    assert "snapshot" in second.detail


def test_markdown_mode_is_skipped(tmp_path: Path) -> None:
    proj = _migrated_project(tmp_path, mode="markdown")
    result = seed_graph_from_docs(str(proj))
    gc.collect()
    assert result.action == "skipped"
    assert "not graph" in result.detail


def test_no_documents_is_skipped(tmp_path: Path) -> None:
    proj = _migrated_project(tmp_path, with_docs=False)
    result = seed_graph_from_docs(str(proj))
    gc.collect()
    assert result.action == "skipped"
    assert "no documents" in result.detail
