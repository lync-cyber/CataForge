"""Backfill YAML front matter on system-generated review reports + research notes.

Pre-this-version projects have ``docs/reviews/{doc,code}/REVIEW-*.md`` and
``docs/reviews/CORRECTIONS-LOG.md`` files written without YAML front matter,
because doc-review / code-review SKILL.md and ``core/corrections.py`` did not
emit a header before this version. The result: ``cataforge docs index`` skips
them as orphans and ``cataforge doctor`` FAILs with the orphan count.

This migration scans the canonical paths, infers ``id`` / ``doc_type`` /
``deps`` from filenames, and prepends a minimal front matter block. Idempotent
— files that already start with ``---`` are skipped untouched. The schema
matches COMMON-RULES §报告 Front Matter 约定:

    docs/reviews/doc/REVIEW-{doc_id}-r{N}.md         doc_type: review
    docs/reviews/code/CODE-REVIEW-{task_id}-r{N}.md  doc_type: code-review
    docs/reviews/CORRECTIONS-LOG.md                  doc_type: correction-log
    docs/research/*.md (no front matter)             doc_type: research

Exit codes:
    0  migration succeeded (or nothing to do)
    1  unexpected error during write
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from cataforge.core.paths import find_project_root
from cataforge.utils.common import ensure_utf8_stdio

REVIEW_RE = re.compile(r"^REVIEW-(?P<doc_id>.+)-r(?P<n>\d+)\.md$")
CODE_REVIEW_RE = re.compile(r"^CODE-REVIEW-(?P<task_id>.+)-r(?P<n>\d+)\.md$")


@dataclass(frozen=True)
class Plan:
    path: Path
    fm_id: str
    doc_type: str
    author: str
    status: str
    deps: list[str]


def _has_front_matter(text: str) -> bool:
    return text.startswith("---\n") or text.startswith("---\r\n")


def _format_front_matter(plan: Plan) -> str:
    deps_yaml = (
        "[]"
        if not plan.deps
        else "[" + ", ".join(f'"{d}"' for d in plan.deps) + "]"
    )
    return (
        "---\n"
        f'id: "{plan.fm_id}"\n'
        f"doc_type: {plan.doc_type}\n"
        f"author: {plan.author}\n"
        f"status: {plan.status}\n"
        f"deps: {deps_yaml}\n"
        "---\n"
    )


def _collect_doc_reviews(reviews_dir: Path) -> list[Plan]:
    plans: list[Plan] = []
    sub = reviews_dir / "doc"
    if not sub.is_dir():
        return plans
    for md in sorted(sub.glob("REVIEW-*.md")):
        m = REVIEW_RE.match(md.name)
        if not m:
            continue
        doc_id = m.group("doc_id")
        n = m.group("n")
        plans.append(
            Plan(
                path=md,
                fm_id=f"review-{doc_id}-r{n}",
                doc_type="review",
                author="reviewer",
                status="approved",
                deps=[doc_id],
            )
        )
    return plans


def _collect_code_reviews(reviews_dir: Path) -> list[Plan]:
    plans: list[Plan] = []
    sub = reviews_dir / "code"
    if not sub.is_dir():
        return plans
    for md in sorted(sub.glob("CODE-REVIEW-*.md")):
        m = CODE_REVIEW_RE.match(md.name)
        if not m:
            continue
        task_id = m.group("task_id")
        n = m.group("n")
        plans.append(
            Plan(
                path=md,
                fm_id=f"code-review-{task_id}-r{n}",
                doc_type="code-review",
                author="reviewer",
                status="approved",
                deps=[task_id],
            )
        )
    return plans


def _collect_corrections_log(reviews_dir: Path) -> list[Plan]:
    log = reviews_dir / "CORRECTIONS-LOG.md"
    if not log.is_file():
        return []
    return [
        Plan(
            path=log,
            fm_id="corrections-log",
            doc_type="correction-log",
            author="cataforge",
            status="approved",
            deps=[],
        )
    ]


def _collect_research_notes(docs_dir: Path) -> list[Plan]:
    plans: list[Plan] = []
    sub = docs_dir / "research"
    if not sub.is_dir():
        return plans
    for md in sorted(sub.glob("*.md")):
        plans.append(
            Plan(
                path=md,
                fm_id=md.stem,
                doc_type="research",
                author="user",
                status="approved",
                deps=[],
            )
        )
    return plans


def collect_plans(project_root: Path) -> list[Plan]:
    """Return all migration plans for the project's canonical review paths."""
    docs_dir = project_root / "docs"
    if not docs_dir.is_dir():
        return []
    reviews_dir = docs_dir / "reviews"
    plans: list[Plan] = []
    plans.extend(_collect_doc_reviews(reviews_dir))
    plans.extend(_collect_code_reviews(reviews_dir))
    plans.extend(_collect_corrections_log(reviews_dir))
    plans.extend(_collect_research_notes(docs_dir))
    return plans


def apply_plan(plan: Plan, *, dry_run: bool) -> str:
    """Apply a single plan. Returns one of: ``written`` / ``skipped`` / ``would-write``."""
    text = plan.path.read_text(encoding="utf-8")
    if _has_front_matter(text):
        return "skipped"
    if dry_run:
        return "would-write"
    new_text = _format_front_matter(plan) + text
    plan.path.write_text(new_text, encoding="utf-8")
    return "written"


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description=(
            "Backfill YAML front matter on legacy review reports + "
            "research notes (idempotent — files already with front matter are "
            "left alone)."
        ),
    )
    parser.add_argument("--project-root", default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing.",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root or str(find_project_root()))
    plans = collect_plans(project_root)
    if not plans:
        print("No review/research files found — nothing to migrate.")
        return 0

    written = 0
    skipped = 0
    would = 0
    for plan in plans:
        try:
            outcome = apply_plan(plan, dry_run=args.dry_run)
        except OSError as e:
            print(f"FAIL {plan.path}: {e}", file=sys.stderr)
            return 1
        rel = plan.path.relative_to(project_root)
        if outcome == "written":
            written += 1
            print(f"  + {rel}  (id={plan.fm_id}, doc_type={plan.doc_type})")
        elif outcome == "would-write":
            would += 1
            print(f"  ~ {rel}  (would write id={plan.fm_id}, doc_type={plan.doc_type})")
        else:
            skipped += 1
            print(f"  = {rel}  (front matter present — skipped)")

    if args.dry_run:
        print(f"\nDry run: {would} would-write, {skipped} already have front matter.")
    else:
        print(f"\nDone: {written} written, {skipped} already had front matter.")
        if written:
            print(
                "Next: run `cataforge docs index` to refresh the chapter index, "
                "then `cataforge doctor` to confirm 0 orphans."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
