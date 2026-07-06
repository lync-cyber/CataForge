"""Graph-mode authoring integrity once graph is the only KG-bearing mode.

Removing hybrid leaves graph as the single mode carrying KG gating, so the
frictions that hybrid let authors dodge by "editing the Markdown back" must
hold hard:

* each document round-trips through finalize per file (no collapse);
* amending one document leaves its siblings byte-for-byte intact;
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

_PRD_DOC = (
    "---\nid: prd\ndoc_type: prd\nstatus: draft\n---\n"
    "# PRD\n\n引言。\n\n## 1. 功能\n\n### F-001 登录\n\n登录功能。\n"
)
_DEVPLAN_DOC = (
    "---\nid: dev-plan\ndoc_type: dev-plan\nstatus: draft\n---\n"
    "# Dev Plan\n\n## 3. 任务卡详细\n\n### T-001 登录\n\n实现登录。\n"
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


def _author_two_docs(proj: Path) -> None:
    cw.author_document(str(proj), _PRD_DOC, source_path="docs/prd/prd.md")
    cw.author_document(str(proj), _DEVPLAN_DOC, source_path="docs/dev-plan/dev-plan.md")
    gc.collect()


class TestFinalizePreservesDocuments:
    def test_each_document_round_trips_per_file(self, tmp_path: Path) -> None:
        """Each document is its own node (distinct id / source_path), so
        finalize reconstructs both files and never folds them into one."""
        proj = _project(tmp_path)
        _author_two_docs(proj)
        cw.finalize(str(proj))
        gc.collect()

        prd_f = proj / "docs" / "prd" / "prd.md"
        dp_f = proj / "docs" / "dev-plan" / "dev-plan.md"
        assert prd_f.is_file() and dp_f.is_file()
        # the dev-plan's task card stayed in its own file
        assert "T-001" in dp_f.read_text(encoding="utf-8")
        assert "T-001" not in prd_f.read_text(encoding="utf-8")

    def test_re_finalize_is_byte_stable(self, tmp_path: Path) -> None:
        proj = _project(tmp_path)
        _author_two_docs(proj)
        cw.finalize(str(proj))
        gc.collect()
        prd_f = proj / "docs" / "prd" / "prd.md"
        dp_f = proj / "docs" / "dev-plan" / "dev-plan.md"
        first = (prd_f.read_bytes(), dp_f.read_bytes())

        cw.finalize(str(proj))
        gc.collect()
        assert (prd_f.read_bytes(), dp_f.read_bytes()) == first
        assert cw.reconcile_check(str(proj)).ok


class TestAmendmentDocumentIsolation:
    def test_amending_one_document_leaves_siblings_intact(self, tmp_path: Path) -> None:
        proj = _project(tmp_path)
        _author_two_docs(proj)
        cw.finalize(str(proj))
        gc.collect()
        prd_f = proj / "docs" / "prd" / "prd.md"
        prd_before = prd_f.read_bytes()

        amended = _DEVPLAN_DOC.replace("实现登录。", "实现登录（含 OAuth）。")
        cw.author_document(str(proj), amended, source_path="docs/dev-plan/dev-plan.md")
        gc.collect()
        cw.finalize(str(proj))
        gc.collect()

        assert prd_f.read_bytes() == prd_before
        dp_text = (proj / "docs" / "dev-plan" / "dev-plan.md").read_text(encoding="utf-8")
        assert "OAuth" in dp_text


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
        cw.author_document(str(proj), _DEVPLAN_DOC, source_path="docs/dev-plan/dev-plan.md")
        gc.collect()
        cw.update_document_meta(str(proj), "dev-plan", status="approved")
        gc.collect()

        # _DEVPLAN_DOC carries status: draft → re-authoring would downgrade approved.
        with pytest.raises(KGValidationError, match="approved"):
            cw.author_document(str(proj), _DEVPLAN_DOC, source_path="docs/dev-plan/dev-plan.md")
        gc.collect()

    def test_re_author_keeping_approved_is_allowed(self, tmp_path: Path) -> None:
        proj = _project(tmp_path)
        cw.author_document(str(proj), _DEVPLAN_DOC, source_path="docs/dev-plan/dev-plan.md")
        gc.collect()
        cw.update_document_meta(str(proj), "dev-plan", status="approved")
        gc.collect()

        approved_doc = _DEVPLAN_DOC.replace("status: draft", "status: approved").replace(
            "实现登录。", "实现登录（修订）。"
        )
        result = cw.author_document(
            str(proj), approved_doc, source_path="docs/dev-plan/dev-plan.md"
        )
        gc.collect()
        assert result.doc_id == "dev-plan"
