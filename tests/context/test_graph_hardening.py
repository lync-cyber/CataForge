"""Graph-mode authoring integrity once graph is the only KG-bearing mode.

Removing hybrid leaves graph as the single mode carrying KG gating, so the
frictions that hybrid let authors dodge by "editing the Markdown back" must
hold hard:

* a split-volume document round-trips through finalize per file (no collapse);
* amending one volume leaves its siblings byte-for-byte intact;
* re-authoring a document atomically replaces its traceability edges;
* an approved document's status is frozen against a content re-author.
"""

from __future__ import annotations

import gc
import json
from pathlib import Path

import pytest

from cataforge.application.context import write as cw
from cataforge.domain.kg import KGConfig, init_store
from cataforge.domain.kg._dispatch import invalidate_cache

_FRAMEWORK = {
    "context": {"mode": "graph", "kg_active_doc_types": ["dev-plan", "prd"]},
    "kg": {"project_id": "p", "title": "T", "process_model": "waterfall"},
    "docs": {"doc_types": {"dev-plan": "dev-plan", "prd": "prd"}},
}

_MAIN_VOL = (
    "---\nid: dev-plan-x\ndoc_type: dev-plan\nstatus: draft\n---\n"
    "# Dev Plan\n\n引言。\n\n## 1. 迭代规划\n\nSprint 概览。\n"
)
_SPRINT_VOL = (
    "---\nid: dev-plan-x-s1\ndoc_type: dev-plan\nstatus: draft\n---\n"
    "# Dev Plan 分卷 S1\n\n## 3. 任务卡详细\n\n### T-001 登录\n\n实现登录。\n"
)


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    gc.collect()
    yield
    invalidate_cache()
    gc.collect()


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / ".cataforge").mkdir(parents=True)
    cfg = KGConfig(store_backend="oxigraph", db_path=proj / ".cataforge" / "kg" / "store")
    init_store(cfg, force=True).close()
    (proj / ".cataforge" / "framework.json").write_text(json.dumps(_FRAMEWORK), encoding="utf-8")
    (proj / "docs").mkdir()
    invalidate_cache()
    gc.collect()
    return proj


def _author_both_volumes(proj: Path) -> None:
    cw.author_document(str(proj), _MAIN_VOL, source_path="docs/dev-plan/dev-plan-x.md")
    cw.author_document(str(proj), _SPRINT_VOL, source_path="docs/dev-plan/dev-plan-x-s1.md")
    gc.collect()


class TestFinalizePreservesVolumes:
    def test_split_volume_round_trips_per_file(self, tmp_path: Path) -> None:
        """Each volume is its own Document (distinct id / source_path), so
        finalize reconstructs both files and never folds them into one."""
        proj = _project(tmp_path)
        _author_both_volumes(proj)
        cw.finalize(str(proj))
        gc.collect()

        main_f = proj / "docs" / "dev-plan" / "dev-plan-x.md"
        s1_f = proj / "docs" / "dev-plan" / "dev-plan-x-s1.md"
        assert main_f.is_file() and s1_f.is_file()
        # the sprint volume's task card stayed in its own file
        assert "T-001" in s1_f.read_text(encoding="utf-8")
        assert "T-001" not in main_f.read_text(encoding="utf-8")

    def test_re_finalize_is_byte_stable(self, tmp_path: Path) -> None:
        proj = _project(tmp_path)
        _author_both_volumes(proj)
        cw.finalize(str(proj))
        gc.collect()
        main_f = proj / "docs" / "dev-plan" / "dev-plan-x.md"
        s1_f = proj / "docs" / "dev-plan" / "dev-plan-x-s1.md"
        first = (main_f.read_bytes(), s1_f.read_bytes())

        cw.finalize(str(proj))
        gc.collect()
        assert (main_f.read_bytes(), s1_f.read_bytes()) == first
        assert cw.reconcile_check(str(proj)).ok


class TestAmendmentVolumeIsolation:
    def test_amending_one_volume_leaves_siblings_intact(self, tmp_path: Path) -> None:
        proj = _project(tmp_path)
        _author_both_volumes(proj)
        cw.finalize(str(proj))
        gc.collect()
        main_f = proj / "docs" / "dev-plan" / "dev-plan-x.md"
        main_before = main_f.read_bytes()

        amended = _SPRINT_VOL.replace("实现登录。", "实现登录（含 OAuth）。")
        cw.author_document(str(proj), amended, source_path="docs/dev-plan/dev-plan-x-s1.md")
        gc.collect()
        cw.finalize(str(proj))
        gc.collect()

        assert main_f.read_bytes() == main_before
        s1_text = (proj / "docs" / "dev-plan" / "dev-plan-x-s1.md").read_text(encoding="utf-8")
        assert "OAuth" in s1_text


class TestRelationIdempotence:
    _PRD = (
        "---\nid: prd\ndoc_type: prd\nstatus: draft\n---\n"
        "# PRD\n\n## 1. 功能\n\n### F-001 登录\n\n依赖 [F-002](prd#§1.F-002)。\n\n"
        "### F-002 注册\n\n注册流程。\n"
    )

    def test_re_author_does_not_accumulate_edges(self, tmp_path: Path) -> None:
        """Authoring the same document twice replaces its traceability edges
        rather than stacking a second copy — reconcile stays clean."""
        proj = _project(tmp_path)
        r1 = cw.author_document(str(proj), self._PRD, source_path="docs/prd/prd.md")
        gc.collect()
        r2 = cw.author_document(str(proj), self._PRD, source_path="docs/prd/prd.md")
        gc.collect()

        assert r1.relations_written == r2.relations_written == 1
        cw.finalize(str(proj))
        gc.collect()
        assert cw.reconcile_check(str(proj)).ok


class TestApprovedStatusFreeze:
    def test_re_author_downgrade_of_approved_is_blocked(self, tmp_path: Path) -> None:
        from cataforge.domain.kg._errors import KGValidationError

        proj = _project(tmp_path)
        cw.author_document(str(proj), _MAIN_VOL, source_path="docs/dev-plan/dev-plan-x.md")
        gc.collect()
        cw.update_document_meta(str(proj), "dev-plan-x", status="approved")
        gc.collect()

        # _MAIN_VOL carries status: draft → re-authoring would downgrade approved.
        with pytest.raises(KGValidationError, match="approved"):
            cw.author_document(str(proj), _MAIN_VOL, source_path="docs/dev-plan/dev-plan-x.md")
        gc.collect()

    def test_re_author_keeping_approved_is_allowed(self, tmp_path: Path) -> None:
        proj = _project(tmp_path)
        cw.author_document(str(proj), _MAIN_VOL, source_path="docs/dev-plan/dev-plan-x.md")
        gc.collect()
        cw.update_document_meta(str(proj), "dev-plan-x", status="approved")
        gc.collect()

        approved_vol = _MAIN_VOL.replace("status: draft", "status: approved").replace(
            "Sprint 概览。", "Sprint 概览（修订）。"
        )
        result = cw.author_document(
            str(proj), approved_vol, source_path="docs/dev-plan/dev-plan-x.md"
        )
        gc.collect()
        assert result.doc_id == "dev-plan-x"
