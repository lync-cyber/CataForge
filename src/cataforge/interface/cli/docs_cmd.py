"""cataforge docs — document tools (section loader + chapter-level index)."""

from __future__ import annotations

import click

from cataforge.core.errors import CataforgeError
from cataforge.interface.cli.helpers import resolve_project_dir, resolve_root
from cataforge.interface.cli.main import cli


def _emit_validate_failures(
    orphans: list[str],
    stale: list[tuple[str, str]],
    xref_errors: list[dict[str, str]],
    alias_conflicts: list[dict[str, str]],
    invalid_ids: list[dict[str, str]],
) -> None:
    """Echo per-category FAIL lines for docs_validate."""
    if orphans:
        click.echo(
            f"FAIL · {len(orphans)} orphan(s) — missing YAML front matter:",
            err=True,
        )
        for rel in orphans:
            click.echo(f"  - {rel}", err=True)

    if stale:
        click.echo(f"FAIL · {len(stale)} stale index entry(ies):", err=True)
        for doc_id, rel in stale:
            click.echo(f"  - {doc_id} → {rel}", err=True)

    if xref_errors:
        click.echo(f"FAIL · {len(xref_errors)} cross-reference error(s):", err=True)
        for e in xref_errors:
            click.echo(
                f"  - {e['doc_id']} ({e['file_path']}) → {e['ref']}: {e['reason']}",
                err=True,
            )

    if alias_conflicts:
        click.echo(f"FAIL · {len(alias_conflicts)} alias conflict(s):", err=True)
        for c in alias_conflicts:
            click.echo(
                f"  - {c['alias']} (claimed by {c['claimed_by']}): {c['reason']}",
                err=True,
            )

    if invalid_ids:
        click.echo(
            f"FAIL · {len(invalid_ids)} invalid id(s) — slug must match [A-Za-z0-9_-]+:",
            err=True,
        )
        for e in invalid_ids:
            click.echo(
                f"  - [{e['kind']}] {e['value']!r} ({e['file_path']}): {e['reason']}",
                err=True,
            )


def _raise_on_nonzero(code: int, command_label: str) -> None:
    """Translate a non-zero return code from a sub-CLI main() into a
    proper :class:`CataforgeError` so the user sees the unified
    ``Error: …`` prefix instead of a raw traceback or silent exit."""
    if code == 0:
        return
    err = CataforgeError(f"`{command_label}` failed (exit code {code}).")
    err.exit_code = code
    raise err


def run_load(
    refs: tuple[str, ...],
    project_root: str | None,
    json_output: bool,
    with_deps: bool,
    budget: int | None,
    *,
    command_label: str,
) -> None:
    """Load Markdown sections by ``doc_id#§N`` references.

    Shared body behind ``context read`` and the ``docs load`` deprecated alias.
    """
    from cataforge.application.context.read import main as context_load_main

    argv = list(refs)
    if project_root:
        argv.extend(["--project-root", str(project_root)])
    if json_output:
        argv.append("--json")
    if with_deps:
        argv.append("--with-deps")
    if budget is not None:
        argv.extend(["--budget", str(budget)])
    _raise_on_nonzero(context_load_main(argv), command_label)


def run_index(
    project_root: str | None,
    doc_file: str | None,
    strict: bool,
    *,
    command_label: str,
) -> None:
    """Build or update the chapter-level JSON index ``docs/.doc-index.json``.

    Shared body behind ``context index`` and the ``docs index`` deprecated alias.
    """
    from cataforge.domain.docs.indexer import main as indexer_main

    argv: list[str] = []
    if project_root:
        argv.extend(["--project-root", str(project_root)])
    if doc_file:
        argv.extend(["--doc-file", doc_file])
    if strict:
        argv.append("--strict")
    _raise_on_nonzero(indexer_main(argv), command_label)


def run_validate(project_root: str | None) -> None:
    """Validate ``docs/.doc-index.json`` integrity without writing to disk.

    Shared body behind ``context validate`` and the ``docs validate`` alias.
    """
    import os

    from cataforge.domain.docs.indexer import (
        INDEX_FILENAME,
        format_stale_deps_warning,
        validate_docs,
    )

    root = project_root or str(resolve_root())
    index_path = os.path.join(root, "docs", INDEX_FILENAME)
    if not os.path.isfile(index_path):
        click.echo(
            f"docs/{INDEX_FILENAME} not found — nothing to validate. "
            "Run `cataforge context index` first if you intend to opt into "
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
    ignored = result.get("ignored", [])
    stale = result["stale"]
    xref_errors = result["xref_errors"]
    alias_conflicts = result["alias_conflicts"]
    invalid_ids = result.get("invalid_ids", [])
    stale_deps = result.get("stale_deps", [])

    if ignored:
        click.echo(f"{len(ignored)} doc(s) excluded by docs/.docignore")

    if not orphans and not stale and not xref_errors and not alias_conflicts and not invalid_ids:
        summary = (
            "OK · 0 orphans · 0 stale entries · 0 xref errors · 0 alias conflicts · 0 invalid ids"
        )
        if stale_deps:
            summary += f" · {len(stale_deps)} stale dep(s)"
        click.echo(summary)
        for line in format_stale_deps_warning(stale_deps):
            click.echo(line, err=True)
        return

    _emit_validate_failures(orphans, stale, xref_errors, alias_conflicts, invalid_ids)

    for line in format_stale_deps_warning(stale_deps):
        click.echo(line, err=True)

    err = CataforgeError(
        f"docs validate failed ({len(orphans)} orphan, {len(stale)} stale, "
        f"{len(xref_errors)} xref, {len(alias_conflicts)} alias, "
        f"{len(invalid_ids)} invalid-id)",
    )
    err.exit_code = 3
    raise err


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
    _emit_deprecation("docs index")
    effective_root = project_root or resolve_project_dir()
    run_index(
        str(effective_root) if effective_root else None,
        doc_file,
        strict,
        command_label="docs index",
    )


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
