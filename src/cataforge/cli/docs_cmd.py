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
def docs_index(project_root: str | None, doc_file: str | None) -> None:
    """Build or update the chapter-level JSON index ``docs/.doc-index.json``."""
    from cataforge.docs.indexer import main as indexer_main

    argv: list[str] = []
    if project_root:
        argv.extend(["--project-root", project_root])
    if doc_file:
        argv.extend(["--doc-file", doc_file])
    _raise_on_nonzero(indexer_main(argv), "docs index")


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
