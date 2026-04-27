"""Tests for `cataforge docs migrate-reviews`."""

from __future__ import annotations

from pathlib import Path

from cataforge.docs.migrate_review_frontmatter import (
    apply_plan,
    collect_plans,
    main,
)


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_collect_plans_finds_all_canonical_paths(tmp_path: Path) -> None:
    _write(tmp_path / "docs" / "reviews" / "doc" / "REVIEW-prd-r1.md", "# A\n")
    _write(tmp_path / "docs" / "reviews" / "code" / "CODE-REVIEW-T-001-r2.md", "# B\n")
    _write(tmp_path / "docs" / "reviews" / "CORRECTIONS-LOG.md", "# C\n")
    _write(tmp_path / "docs" / "research" / "raw-requirements-v1.md", "# D\n")

    plans = collect_plans(tmp_path)
    by_id = {p.fm_id: p for p in plans}

    assert by_id["review-prd-r1"].doc_type == "review"
    assert by_id["review-prd-r1"].deps == ["prd"]
    assert by_id["code-review-T-001-r2"].doc_type == "code-review"
    assert by_id["code-review-T-001-r2"].deps == ["T-001"]
    assert by_id["corrections-log"].doc_type == "correction-log"
    assert by_id["corrections-log"].deps == []
    assert by_id["raw-requirements-v1"].doc_type == "research"


def test_apply_plan_writes_front_matter(tmp_path: Path) -> None:
    _write(tmp_path / "docs" / "reviews" / "doc" / "REVIEW-arch-r1.md", "# title\nbody\n")

    plans = collect_plans(tmp_path)
    assert len(plans) == 1
    outcome = apply_plan(plans[0], dry_run=False)
    assert outcome == "written"

    text = plans[0].path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert 'id: "review-arch-r1"' in text
    assert "doc_type: review" in text
    assert 'deps: ["arch"]' in text
    assert "# title\nbody\n" in text


def test_apply_plan_idempotent_skips_files_with_front_matter(tmp_path: Path) -> None:
    existing = (
        "---\n"
        'id: "review-prd-r1"\n'
        "doc_type: review\n"
        "author: reviewer\n"
        "status: approved\n"
        "deps: [\"prd\"]\n"
        "---\n"
        "# already has fm\n"
    )
    _write(tmp_path / "docs" / "reviews" / "doc" / "REVIEW-prd-r1.md", existing)

    plans = collect_plans(tmp_path)
    outcome = apply_plan(plans[0], dry_run=False)
    assert outcome == "skipped"
    assert plans[0].path.read_text(encoding="utf-8") == existing


def test_dry_run_does_not_modify_files(tmp_path: Path) -> None:
    body = "# untouched\n"
    f = tmp_path / "docs" / "reviews" / "doc" / "REVIEW-prd-r1.md"
    _write(f, body)
    plans = collect_plans(tmp_path)
    outcome = apply_plan(plans[0], dry_run=True)
    assert outcome == "would-write"
    assert f.read_text(encoding="utf-8") == body


def test_main_returns_zero_when_nothing_to_migrate(tmp_path: Path) -> None:
    rc = main(["--project-root", str(tmp_path)])
    assert rc == 0


def test_main_writes_front_matter_for_real(tmp_path: Path) -> None:
    _write(tmp_path / "docs" / "reviews" / "CORRECTIONS-LOG.md", "# Corrections Log\n")
    _write(
        tmp_path / "docs" / "reviews" / "code" / "CODE-REVIEW-T-001-r1.md",
        "# code review\n",
    )

    rc = main(["--project-root", str(tmp_path)])
    assert rc == 0

    log_text = (tmp_path / "docs" / "reviews" / "CORRECTIONS-LOG.md").read_text(
        encoding="utf-8"
    )
    assert log_text.startswith("---\n")
    assert "doc_type: correction-log" in log_text

    cr_text = (
        tmp_path / "docs" / "reviews" / "code" / "CODE-REVIEW-T-001-r1.md"
    ).read_text(encoding="utf-8")
    assert cr_text.startswith("---\n")
    assert "doc_type: code-review" in cr_text


def test_migration_output_indexable(tmp_path: Path) -> None:
    """Front matter written by migration must round-trip through the indexer."""
    from cataforge.docs.indexer import find_orphan_docs

    _write(tmp_path / "docs" / "reviews" / "doc" / "REVIEW-prd-r1.md", "# A\n## §1\n")
    _write(
        tmp_path / "docs" / "reviews" / "code" / "CODE-REVIEW-T-001-r1.md",
        "# B\n## §1\n",
    )
    _write(tmp_path / "docs" / "reviews" / "CORRECTIONS-LOG.md", "# C\n## §1\n")
    _write(tmp_path / "docs" / "research" / "raw-requirements-v1.md", "# D\n## §1\n")

    assert len(find_orphan_docs(str(tmp_path))) == 4

    main(["--project-root", str(tmp_path)])

    assert find_orphan_docs(str(tmp_path)) == []
