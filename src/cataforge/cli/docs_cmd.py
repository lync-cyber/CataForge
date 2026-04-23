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
def docs_load(refs: tuple[str, ...], project_root: str | None) -> None:
    """Load Markdown sections by ``doc_id#§N`` references.

    REFS: one or more ``doc_id#§N[.item]`` references — see
    ``docs/reference/docs-refs.md`` for the grammar.
    """
    from cataforge.docs.loader import main as loader_main

    argv = list(refs)
    if project_root:
        argv.extend(["--project-root", project_root])
    _raise_on_nonzero(loader_main(argv), "docs load")


@docs_group.command("index")
@click.option("--project-root", default=None, help="Project root directory.")
@click.option(
    "--doc-file",
    default=None,
    help="Incremental update for a single file (otherwise rebuild the full index).",
)
def docs_index(project_root: str | None, doc_file: str | None) -> None:
    """Build or update the chapter-level JSON index under ``docs/.nav/``."""
    from cataforge.docs.indexer import main as indexer_main

    argv: list[str] = []
    if project_root:
        argv.extend(["--project-root", project_root])
    if doc_file:
        argv.extend(["--doc-file", doc_file])
    _raise_on_nonzero(indexer_main(argv), "docs index")
