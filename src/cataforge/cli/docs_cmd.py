"""cataforge docs — document tools."""

from __future__ import annotations

import click

from cataforge.cli.main import cli


@cli.group("docs")
def docs_group() -> None:
    """Document section loader and index builder."""


@docs_group.command("load")
@click.argument("refs", nargs=-1, required=True)
@click.option("--project-root", default=None, help="Project root directory")
def docs_load(refs: tuple[str, ...], project_root: str | None) -> None:
    """Load Markdown sections by doc_id#§N references."""
    from cataforge.docs.loader import main as loader_main

    argv = list(refs)
    if project_root:
        argv.extend(["--project-root", project_root])
    code = loader_main(argv)
    raise SystemExit(code)


@docs_group.command("index")
@click.option("--project-root", default=None, help="Project root directory")
@click.option("--doc-file", default=None, help="Incremental update for a single file")
def docs_index(project_root: str | None, doc_file: str | None) -> None:
    """Build or update the chapter-level JSON index."""
    from cataforge.docs.indexer import main as indexer_main

    argv: list[str] = []
    if project_root:
        argv.extend(["--project-root", project_root])
    if doc_file:
        argv.extend(["--doc-file", doc_file])
    code = indexer_main(argv)
    raise SystemExit(code)
