"""Unit tests for cataforge.docs.migrate_review_frontmatter."""

from __future__ import annotations

from pathlib import Path

from cataforge.docs.migrate_review_frontmatter import (
    Plan,
    _format_front_matter,
    _has_front_matter,
    apply_plan,
    collect_plans,
)

# ---------------------------------------------------------------------------
# _has_front_matter
# ---------------------------------------------------------------------------


def test_has_front_matter_detects_opening_triple_dash():
    assert _has_front_matter("---\nid: foo\n---\nbody\n")


def test_has_front_matter_returns_false_for_body_only():
    assert not _has_front_matter("# Just a heading\n\nSome body.\n")


# ---------------------------------------------------------------------------
# _format_front_matter — content field assertions
# ---------------------------------------------------------------------------


def test_format_front_matter_fields():
    plan = Plan(
        path=Path("/dummy/REVIEW-prd-r1.md"),
        fm_id="review-prd-r1",
        doc_type="review",
        author="reviewer",
        status="approved",
        deps=["prd"],
    )
    fm = _format_front_matter(plan)
    assert fm.startswith("---\n")
    assert 'id: "review-prd-r1"' in fm
    assert "doc_type: review" in fm
    assert "author: reviewer" in fm
    assert "status: approved" in fm
    assert '"prd"' in fm


def test_format_front_matter_empty_deps():
    plan = Plan(
        path=Path("/dummy/CORRECTIONS-LOG.md"),
        fm_id="corrections-log",
        doc_type="correction-log",
        author="cataforge",
        status="approved",
        deps=[],
    )
    fm = _format_front_matter(plan)
    assert "deps: []" in fm


# ---------------------------------------------------------------------------
# apply_plan — written path writes frontmatter + original body
# ---------------------------------------------------------------------------


def test_apply_plan_writes_frontmatter_and_preserves_body(tmp_path: Path):
    md = tmp_path / "REVIEW-prd-r1.md"
    md.write_text("# Review content\n\nSome analysis.\n", encoding="utf-8")

    plan = Plan(
        path=md,
        fm_id="review-prd-r1",
        doc_type="review",
        author="reviewer",
        status="approved",
        deps=["prd"],
    )

    outcome = apply_plan(plan, dry_run=False)
    assert outcome == "written"

    written = md.read_text(encoding="utf-8")
    assert written.startswith("---\n")
    assert 'id: "review-prd-r1"' in written
    assert "# Review content" in written
    assert "Some analysis." in written


# ---------------------------------------------------------------------------
# apply_plan — skips files that already have frontmatter (idempotent)
# ---------------------------------------------------------------------------


def test_apply_plan_skips_existing_frontmatter(tmp_path: Path):
    md = tmp_path / "REVIEW-prd-r1.md"
    original = "---\nid: review-prd-r1\n---\n# Body\n"
    md.write_text(original, encoding="utf-8")

    plan = Plan(
        path=md,
        fm_id="review-prd-r1",
        doc_type="review",
        author="reviewer",
        status="approved",
        deps=["prd"],
    )

    outcome = apply_plan(plan, dry_run=False)
    assert outcome == "skipped"
    assert md.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# apply_plan — dry_run does not write
# ---------------------------------------------------------------------------


def test_apply_plan_dry_run_does_not_write(tmp_path: Path):
    md = tmp_path / "REVIEW-prd-r1.md"
    body = "# Review\nNo frontmatter.\n"
    md.write_text(body, encoding="utf-8")

    plan = Plan(
        path=md,
        fm_id="review-prd-r1",
        doc_type="review",
        author="reviewer",
        status="approved",
        deps=["prd"],
    )

    outcome = apply_plan(plan, dry_run=True)
    assert outcome == "would-write"
    assert md.read_text(encoding="utf-8") == body


# ---------------------------------------------------------------------------
# collect_plans — docs dir does not exist → empty list
# ---------------------------------------------------------------------------


def test_collect_plans_empty_when_no_docs_dir(tmp_path: Path):
    assert collect_plans(tmp_path) == []


# ---------------------------------------------------------------------------
# collect_plans — doc review files are discovered
# ---------------------------------------------------------------------------


def test_collect_plans_discovers_doc_reviews(tmp_path: Path):
    review_dir = tmp_path / "docs" / "reviews" / "doc"
    review_dir.mkdir(parents=True)
    (review_dir / "REVIEW-prd-r1.md").write_text("# Review\n", encoding="utf-8")
    (review_dir / "REVIEW-arch-r2.md").write_text("# Review\n", encoding="utf-8")

    plans = collect_plans(tmp_path)
    ids = [p.fm_id for p in plans]
    assert "review-prd-r1" in ids
    assert "review-arch-r2" in ids


# ---------------------------------------------------------------------------
# collect_plans — corrections log and research notes included
# ---------------------------------------------------------------------------


def test_collect_plans_discovers_corrections_log_and_research(tmp_path: Path):
    reviews_dir = tmp_path / "docs" / "reviews"
    reviews_dir.mkdir(parents=True)
    (reviews_dir / "CORRECTIONS-LOG.md").write_text("# Log\n", encoding="utf-8")

    research_dir = tmp_path / "docs" / "research"
    research_dir.mkdir(parents=True)
    (research_dir / "spike-auth.md").write_text("# Spike\n", encoding="utf-8")

    plans = collect_plans(tmp_path)
    ids = [p.fm_id for p in plans]
    assert "corrections-log" in ids
    assert "spike-auth" in ids
