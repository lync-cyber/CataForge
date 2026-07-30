"""cataforge context docs-index gates — index, validate."""

from __future__ import annotations

import click

from cataforge.interface.cli.context import context_group
from cataforge.interface.cli.context._shared import _rooted


@context_group.command("index")
@click.option("--project-root", default=None)
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
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Read-only integrity gate: validate the existing index without "
    "rebuilding or writing. Equivalent to `context validate`.",
)
@click.pass_context
def context_index(
    ctx: click.Context,
    project_root: str | None,
    doc_file: str | None,
    strict: bool,
    dry_run: bool,
) -> None:
    """Build or update the chapter-level JSON index ``docs/.doc-index.json``."""
    from cataforge.interface.cli._support.doc_io import run_index

    run_index(
        _rooted(ctx, project_root),
        doc_file,
        strict,
        dry_run=dry_run,
        command_label="context index",
    )


@context_group.command("validate")
@click.option("--project-root", default=None)
@click.pass_context
def context_validate(ctx: click.Context, project_root: str | None) -> None:
    """Validate ``docs/.doc-index.json`` integrity without writing to disk.

    Operates on the index (not the live KG store — that is ``kg validate``).
    Equivalent to ``context index --strict`` but read-only — useful as a
    pre-commit / CI gate that fails fast on:

    \b
    - orphan docs (markdown files missing YAML front matter)
    - stale index entries (file_path no longer on disk)
    - cross-reference errors (frontmatter ``deps`` that don't resolve)
    - alias conflicts (duplicate / shadowed alias claims)
    - invalid ids (doc_id / alias containing '.' or other non-slug chars)

    Exits 0 when clean, 3 when any failure is found.
    """
    from cataforge.interface.cli._support.doc_io import run_validate

    run_validate(_rooted(ctx, project_root))
