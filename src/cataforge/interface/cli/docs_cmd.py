"""cataforge docs — document tools (section loader + chapter-level index)."""

from __future__ import annotations

import click

from cataforge.interface.cli._support.doc_io import (
    _raise_on_nonzero,
    run_index,
    run_load,
    run_validate,
)
from cataforge.interface.cli._support.helpers import resolve_project_dir, resolve_root
from cataforge.interface.cli.main import cli

_DEPRECATION_HINTS = {
    "docs load": "deprecated: use 'cataforge context read' instead",
    "docs index": "deprecated: use 'cataforge context index' instead",
    "docs validate": "deprecated: use 'cataforge context validate' instead",
}


def _emit_deprecation(command_label: str) -> None:
    """Append a one-line deprecation hint on stderr; stdout is untouched."""
    click.echo(_DEPRECATION_HINTS[command_label], err=True)


@cli.group("docs")
def docs_group() -> None:
    """Deprecated aliases for the ``context`` read/index family.

    ``load`` / ``index`` / ``validate`` forward to ``cataforge context``
    verbatim (exit codes preserved) and print a deprecation hint on stderr.
    ``migrate-nav`` / ``migrate-reviews`` remain the canonical migration entry
    points.
    """


@docs_group.command("load", hidden=True)
@click.argument("refs", nargs=-1, required=True)
@click.option("--project-root", default=None, help="Project root directory.")
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help=(
        "Emit a JSON array instead of '=== <ref> ===' separators "
        "(avoids collisions when section content contains '===')."
    ),
)
@click.option(
    "--with-deps",
    "with_deps",
    is_flag=True,
    default=False,
    help="Also load dependency refs declared in .doc-index.json (depth ≤ 2).",
)
@click.option(
    "--budget",
    type=int,
    default=None,
    metavar="TOKENS",
    help=(
        "Token budget; refs exceeding the budget are listed on stderr as [DEFERRED] and not loaded."
    ),
)
def docs_load(
    refs: tuple[str, ...],
    project_root: str | None,
    json_output: bool,
    with_deps: bool,
    budget: int | None,
) -> None:
    """Load Markdown sections by ``doc_id#§N`` references.

    REFS: one or more ``doc_id#§N[.item]`` references. Grammar:
    ``doc_id#§N`` (top section), ``doc_id#§N.M`` (subsection), or
    ``doc_id#§N.ITEM-xxx`` (item, e.g. ``prd#§2.F-001``).
    """
    _emit_deprecation("docs load")
    effective_root = project_root or resolve_project_dir()
    run_load(
        refs,
        str(effective_root) if effective_root else None,
        json_output,
        with_deps,
        budget,
        command_label="docs load",
    )


@docs_group.command("index", hidden=True)
@click.option("--project-root", default=None, help="Project root directory.")
@click.option(
    "--doc-file",
    default=None,
    help="Incremental update for a single file (otherwise rebuild the full index).",
)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Exit non-zero (3) if any docs/**/*.md is skipped for missing YAML "
    "front matter — useful as a CI gate.",
)
def docs_index(project_root: str | None, doc_file: str | None, strict: bool) -> None:
    """Build or update the chapter-level JSON index ``docs/.doc-index.json``."""
    _emit_deprecation("docs index")
    effective_root = project_root or resolve_project_dir()
    run_index(
        str(effective_root) if effective_root else None,
        doc_file,
        strict,
        command_label="docs index",
    )


@docs_group.command("validate", hidden=True)
@click.option("--project-root", default=None, help="Project root directory.")
def docs_validate(project_root: str | None) -> None:
    """Validate ``docs/.doc-index.json`` integrity without writing to disk.

    Equivalent to ``docs index --strict`` but read-only — useful as a
    pre-commit / CI gate that fails fast on:

    \b
    - orphan docs (markdown files missing YAML front matter)
    - stale index entries (file_path no longer on disk)
    - cross-reference errors (frontmatter ``deps`` that don't resolve)
    - alias conflicts (duplicate / shadowed alias claims)
    - invalid ids (doc_id / alias containing '.' or other non-slug chars)

    Exits 0 when clean, 3 when any failure is found.
    """
    _emit_deprecation("docs validate")
    run_validate(project_root or str(resolve_root()))


@docs_group.command("migrate-nav")
@click.option("--project-root", default=None, help="Project root directory.")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Parse and report only — do not archive, delete, or rebuild.",
)
def docs_migrate_nav(project_root: str | None, dry_run: bool) -> None:
    """Migrate legacy ``docs/NAV-INDEX.md`` to ``docs/.doc-index.json``.

    Archives the markdown nav under ``.cataforge/.archive/`` then runs
    ``cataforge docs index`` to produce the canonical machine index.
    Surfaces any doc_id present in NAV but missing on disk.
    """
    from cataforge.domain.docs.migrate_nav import main as migrate_main

    argv: list[str] = []
    effective_root = project_root or resolve_project_dir()
    if effective_root:
        argv.extend(["--project-root", str(effective_root)])
    if dry_run:
        argv.append("--dry-run")
    _raise_on_nonzero(migrate_main(argv), "docs migrate-nav")


@docs_group.command("migrate-reviews")
@click.option("--project-root", default=None, help="Project root directory.")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Report what would change without writing.",
)
def docs_migrate_reviews(project_root: str | None, dry_run: bool) -> None:
    """Backfill YAML front matter on legacy review reports + research notes.

    Pre-this-version review reports (``docs/reviews/{doc,code}/REVIEW-*.md``,
    ``docs/reviews/CORRECTIONS-LOG.md``) and ad-hoc research notes
    (``docs/research/*.md``) were written without YAML front matter, so
    ``cataforge docs index`` skipped them as orphans and ``cataforge doctor``
    counted them toward its FAIL gate. This migration prepends a minimal
    front matter block conformant with COMMON-RULES §报告 Front Matter 约定.

    Idempotent — files that already start with ``---`` are left untouched.
    """
    from cataforge.domain.docs.migrate_review_frontmatter import main as migrate_main

    argv: list[str] = []
    effective_root = project_root or resolve_project_dir()
    if effective_root:
        argv.extend(["--project-root", str(effective_root)])
    if dry_run:
        argv.append("--dry-run")
    _raise_on_nonzero(migrate_main(argv), "docs migrate-reviews")
