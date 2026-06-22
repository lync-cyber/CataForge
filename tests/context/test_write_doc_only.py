"""Write-lifecycle routing under ``context.mode = markdown``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.application.context import write as cw
from cataforge.core.errors import CataforgeError
from cataforge.domain.kg._dispatch import invalidate_cache


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    yield
    invalidate_cache()


def _doc(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _doc_only_project(tmp_path: Path) -> Path:
    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"mode": "markdown"}}), encoding="utf-8"
    )
    _doc(
        proj,
        "docs/prd/prd.md",
        "---\nid: prd\ndoc_type: prd\n---\n# PRD\n\n## §1 概览\n\nscope\n",
    )
    _doc(
        proj,
        "docs/arch/arch.md",
        "---\nid: arch\ndoc_type: arch\n---\n# ARCH\n\n## §1 概览\n\ndesign\n",
    )
    return proj


# ---- finalize / ingest → docs index rebuild ---------------------------------


def test_finalize_rebuilds_doc_index(tmp_path: Path) -> None:
    proj = _doc_only_project(tmp_path)
    result = cw.finalize(str(proj))
    assert isinstance(result, cw.DocIndexResult)
    assert result.indexed_count == 2
    index = json.loads((proj / "docs" / ".doc-index.json").read_text(encoding="utf-8"))
    assert set(index["documents"]) == {"prd", "arch"}


def test_finalize_never_creates_graph_store(tmp_path: Path) -> None:
    proj = _doc_only_project(tmp_path)
    cw.finalize(str(proj))
    assert not (proj / ".cataforge" / "kg").exists()


def test_ingest_rebuilds_doc_index(tmp_path: Path) -> None:
    proj = _doc_only_project(tmp_path)
    result = cw.ingest(str(proj))
    assert isinstance(result, cw.DocIndexResult)
    assert result.indexed_count == 2
    assert (proj / "docs" / ".doc-index.json").is_file()


# ---- reconcile → index integrity validation ---------------------------------


def test_reconcile_clean_after_finalize(tmp_path: Path) -> None:
    proj = _doc_only_project(tmp_path)
    cw.finalize(str(proj))
    report = cw.reconcile_check(str(proj))
    assert report.ok
    assert report.overall_divergence_count == 0


def test_reconcile_reports_orphan_as_divergence(tmp_path: Path) -> None:
    proj = _doc_only_project(tmp_path)
    cw.finalize(str(proj))
    _doc(proj, "docs/research/orphan.md", "# no front matter\n")
    report = cw.reconcile_check(str(proj))
    assert not report.ok
    assert report.overall_divergence_count == 1
    assert report.issue_counts["orphans"] == 1


def test_reconcile_reports_stale_entry_as_divergence(tmp_path: Path) -> None:
    proj = _doc_only_project(tmp_path)
    cw.finalize(str(proj))
    (proj / "docs" / "arch" / "arch.md").unlink()
    report = cw.reconcile_check(str(proj))
    assert not report.ok
    assert report.issue_counts["stale"] == 1


def test_reconcile_missing_index_raises_with_index_hint(tmp_path: Path) -> None:
    proj = _doc_only_project(tmp_path)
    with pytest.raises(CataforgeError, match="docs index") as exc_info:
        cw.reconcile_check(str(proj))
    assert exc_info.value.exit_code == 2
    assert "kg init" not in str(exc_info.value)


# ---- entity / narrative authoring → configuration error ---------------------


def test_author_entity_rejected_with_mode_message(tmp_path: Path) -> None:
    proj = _doc_only_project(tmp_path)
    with pytest.raises(cw.ContextModeError, match="context.mode") as exc_info:
        cw.author_entity(str(proj), entity_id="F-001", class_name="Feature", title="登录")
    assert "kg init" not in str(exc_info.value)
    assert not (proj / ".cataforge" / "kg").exists()


def test_write_narrative_rejected_with_mode_message(tmp_path: Path) -> None:
    proj = _doc_only_project(tmp_path)
    with pytest.raises(cw.ContextModeError, match="context.mode") as exc_info:
        cw.write_narrative(str(proj), doc_id="arch", anchor="§1 概览", narrative="文本")
    assert "kg init" not in str(exc_info.value)
    assert not (proj / ".cataforge" / "kg").exists()
