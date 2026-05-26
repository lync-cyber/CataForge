"""cataforge kg — knowledge graph store lifecycle (sub-PR 2 scope).

Sub-PR 2 ships only `kg init`. The remaining `kg ingest / export / validate /
repair / reconcile / snapshot / rollback / diff` subcommands (task-5 §5.1)
land in sub-PRs 3..5 next to the runtime logic they wrap.
"""
from __future__ import annotations

from pathlib import Path

import click

from cataforge.cli.errors import CataforgeError
from cataforge.cli.main import cli


@cli.group("kg")
def kg_group() -> None:
    """Knowledge graph store management (0.5.0 Alpha)."""


@kg_group.command("init")
@click.option(
    "--db-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path(".cataforge/kg/store"),
    show_default=True,
    help="Filesystem path for the RocksDB-backed Oxigraph store.",
)
@click.option(
    "--backend",
    type=click.Choice(["oxigraph", "memory"]),
    default="oxigraph",
    show_default=True,
    help=(
        "Store backend. `oxigraph` creates a persistent RocksDB store at "
        "--db-path; `memory` is for tests only and exits without writing "
        "to disk."
    ),
)
@click.option(
    "--governance",
    is_flag=True,
    default=False,
    help=(
        "Also bootstrap the governance sub-ontology's class hierarchy. "
        "Default off — business-only mode for downstream user projects."
    ),
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite an existing store at --db-path.",
)
def kg_init(db_path: Path, backend: str, governance: bool, force: bool) -> None:
    """Initialize a new KG store with the rdfs:subClassOf hierarchy loaded.

    Bootstrap triples close the subclass-closure gap left by pyoxigraph's
    lack of RDFS entailment (spike-2 §2.1) — without them, queries like
    `?s a/rdfs:subClassOf* cf:Screen` would return zero `cf:Page` rows
    even when Page instances exist.
    """
    from cataforge.kg import (
        KGConfig,
        KGStoreAlreadyExistsError,
        init_store,
    )

    config = KGConfig(
        store_backend=backend,  # type: ignore[arg-type]
        db_path=db_path,
        governance=governance,
    )

    try:
        handle = init_store(config, force=force)
    except KGStoreAlreadyExistsError as exc:
        err = CataforgeError(str(exc))
        err.exit_code = 1
        raise err from exc

    triple_count = sum(1 for _ in handle.raw.quads_for_pattern(None, None, None, None))
    handle.close()

    if backend == "memory":
        click.echo(
            f"OK: bootstrapped in-memory store with {triple_count} "
            f"rdfs:subClassOf triples (will not persist)."
        )
    else:
        click.echo(
            f"OK: initialized KG store at {db_path} with {triple_count} "
            f"rdfs:subClassOf triples."
        )
