"""check_status_provenance — an approved doc must carry a review-report trail."""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker


def _doc(tmp_path: Path, status: str, doc_id: str = "prd-x") -> Path:
    f = tmp_path / f"{doc_id}.md"
    f.write_text(
        f"---\nid: {doc_id}\nauthor: product-manager\nstatus: {status}\n"
        f"deps: []\nconsumers: []\n---\n# 标题\n",
        encoding="utf-8",
    )
    return f


def _review_report(tmp_path: Path, doc_id: str = "prd-x") -> None:
    reviews = tmp_path / "reviews" / "doc"
    reviews.mkdir(parents=True, exist_ok=True)
    (reviews / f"REVIEW-{doc_id}-r1.md").write_text(
        f"---\nid: review-{doc_id}-r1\ndoc_type: review\nauthor: reviewer\n"
        f'status: approved\ndeps: ["{doc_id}"]\n---\n# 审查\n',
        encoding="utf-8",
    )


def test_approved_without_review_report_fails(tmp_path: Path) -> None:
    f = _doc(tmp_path, "approved")
    c = DocChecker("prd", str(f), docs_dir=str(tmp_path))
    c.check_status_provenance()
    assert any("审查报告" in e for e in c.errors), c.errors


def test_approved_with_review_report_passes(tmp_path: Path) -> None:
    _review_report(tmp_path)
    f = _doc(tmp_path, "approved")
    c = DocChecker("prd", str(f), docs_dir=str(tmp_path))
    c.check_status_provenance()
    assert c.errors == [], c.errors


def test_draft_passes_without_report(tmp_path: Path) -> None:
    f = _doc(tmp_path, "draft")
    c = DocChecker("prd", str(f), docs_dir=str(tmp_path))
    c.check_status_provenance()
    assert c.errors == []


def test_report_doc_types_exempt(tmp_path: Path) -> None:
    f = tmp_path / "REVIEW-prd-x-r1.md"
    f.write_text(
        "---\nid: review-prd-x-r1\nauthor: reviewer\nstatus: approved\ndeps: []\n---\n# 审查\n",
        encoding="utf-8",
    )
    c = DocChecker("review", str(f), docs_dir=str(tmp_path))
    c.check_status_provenance()
    assert c.errors == []


def test_split_volume_exempt(tmp_path: Path) -> None:
    f = tmp_path / "prd-x-f001-f008.md"
    f.write_text(
        "---\nid: prd-x-f001-f008\nauthor: product-manager\nstatus: approved\n"
        "deps: []\nconsumers: []\nvolume: features\nsplit_from: prd-x\n---\n# 分卷\n",
        encoding="utf-8",
    )
    c = DocChecker("prd", str(f), docs_dir=str(tmp_path), volume_type="features")
    c.check_status_provenance()
    assert c.errors == []
