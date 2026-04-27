"""cataforge docs — document tools (section loader + chapter-level index)."""

from __future__ import annotations

import click

from cataforge.cli.errors import CataforgeError
from cataforge.cli.main import cli


def _raise_on_nonzero(code: int, command_label: str) -> None:
    """Translate a non-zero return code from a sub-CLI main() into a
    proper :class:`CataforgeError` so the user sees the unified
    ``Error: …`` prefix instead of a raw traceback or silent exit."""
    if code == 0:
        return
    err = CataforgeError(f"`{command_label}` failed (exit code {code}).")
    err.exit_code = code
    raise err


@cli.group("docs")
def docs_group() -> None:
    """Document section loader and chapter-level index builder.

    These are thin wrappers over ``cataforge.docs.loader`` /
    ``cataforge.docs.indexer``; exit codes are preserved verbatim.
    """


@docs_group.command("load")
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
        "Token budget; refs exceeding the budget are listed on stderr as "
        "[DEFERRED] and not loaded."
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
    from cataforge.docs.loader import main as loader_main

    argv = list(refs)
    if project_root:
        argv.extend(["--project-root", project_root])
    if json_output:
        argv.append("--json")
    if with_deps:
        argv.append("--with-deps")
    if budget is not None:
        argv.extend(["--budget", str(budget)])
    _raise_on_nonzero(loader_main(argv), "docs load")


@docs_group.command("index")
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
    from cataforge.docs.indexer import main as indexer_main

    argv: list[str] = []
    if project_root:
        argv.extend(["--project-root", project_root])
    if doc_file:
        argv.extend(["--doc-file", doc_file])
    if strict:
        argv.append("--strict")
    _raise_on_nonzero(indexer_main(argv), "docs index")


@docs_group.command("validate")
@click.option("--project-root", default=None, help="Project root directory.")
def docs_validate(project_root: str | None) -> None:
    """Validate ``docs/.doc-index.json`` integrity without writing to disk.

    Equivalent to ``docs index --strict`` but read-only — useful as a
    pre-commit / CI gate that fails fast on:

    \b
    - orphan docs (markdown files missing YAML front matter)
    - stale index entries (file_path no longer on disk)
    - cross-reference errors (frontmatter ``deps`` that don't resolve)

    Exits 0 when clean, 3 when any failure is found.
    """
    import os

    from cataforge.core.paths import find_project_root
    from cataforge.docs.indexer import INDEX_FILENAME, validate_docs

    root = project_root or str(find_project_root())
    index_path = os.path.join(root, "docs", INDEX_FILENAME)
    if not os.path.isfile(index_path):
        click.echo(
            f"docs/{INDEX_FILENAME} not found — nothing to validate. "
            "Run `cataforge docs index` first if you intend to opt into "
            "CataForge-managed docs.",
            err=True,
        )
        err = CataforgeError(
            f"docs/{INDEX_FILENAME} not found at {root}",
        )
        err.exit_code = 2
        raise err

    result = validate_docs(root)
    orphans = result["orphans"]
    stale = result["stale"]
    xref_errors = result["xref_errors"]
    alias_conflicts = result["alias_conflicts"]

    if not orphans and not stale and not xref_errors and not alias_conflicts:
        click.echo(
            "OK · 0 orphans · 0 stale entries · 0 xref errors · 0 alias conflicts"
        )
        return

    if orphans:
        click.echo(
            f"FAIL · {len(orphans)} orphan(s) — missing YAML front matter:",
            err=True,
        )
        for rel in orphans:
            click.echo(f"  - {rel}", err=True)

    if stale:
        click.echo(
            f"FAIL · {len(stale)} stale index entry(ies):", err=True,
        )
        for doc_id, rel in stale:
            click.echo(f"  - {doc_id} → {rel}", err=True)

    if xref_errors:
        click.echo(
            f"FAIL · {len(xref_errors)} cross-reference error(s):", err=True,
        )
        for e in xref_errors:
            click.echo(
                f"  - {e['doc_id']} ({e['file_path']}) → {e['ref']}: {e['reason']}",
                err=True,
            )

    if alias_conflicts:
        click.echo(
            f"FAIL · {len(alias_conflicts)} alias conflict(s):", err=True,
        )
        for c in alias_conflicts:
            click.echo(
                f"  - {c['alias']} (claimed by {c['claimed_by']}): {c['reason']}",
                err=True,
            )

    err = CataforgeError(
        f"docs validate failed ({len(orphans)} orphan, {len(stale)} stale, "
        f"{len(xref_errors)} xref, {len(alias_conflicts)} alias)",
    )
    err.exit_code = 3
    raise err


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
    from cataforge.docs.migrate_nav import main as migrate_main

    argv: list[str] = []
    if project_root:
        argv.extend(["--project-root", project_root])
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
    from cataforge.docs.migrate_review_frontmatter import main as migrate_main

    argv: list[str] = []
    if project_root:
        argv.extend(["--project-root", project_root])
    if dry_run:
        argv.append("--dry-run")
    _raise_on_nonzero(migrate_main(argv), "docs migrate-reviews")
