"""cataforge kg store lifecycle — init, snapshot, rollback, repair."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    pass

from cataforge.core.errors import (
    KGStoreError,
    KGVerificationError,
)
from cataforge.core.paths import KG_STORE_REL
from cataforge.interface.cli.helpers import root_relative_default
from cataforge.interface.cli.kg import kg_group
from cataforge.interface.cli.kg._options import db_path_option, db_path_ro_option


@kg_group.command("init")
@db_path_option()
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
@click.pass_context
def kg_init(
    ctx: click.Context, db_path: Path, backend: str, governance: bool, force: bool
) -> None:
    """Initialize a new KG store with the rdfs:subClassOf hierarchy loaded.

    Bootstrap triples close the subclass-closure gap left by pyoxigraph's
    lack of RDFS entailment — without them, queries like
    `?s a/rdfs:subClassOf* cf:Screen` would return zero `cf:Page` rows
    even when Page instances exist.
    """
    db_path = root_relative_default(ctx, "db_path", db_path, rel=KG_STORE_REL)

    from cataforge.domain.kg import (
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
        raise KGStoreError(str(exc)) from exc

    triple_count = sum(1 for _ in handle.raw.quads_for_pattern(None, None, None, None))
    handle.close()

    if backend == "memory":
        click.echo(
            f"OK: bootstrapped in-memory store with {triple_count} "
            f"rdfs:subClassOf triples (will not persist)."
        )
    else:
        click.echo(
            f"OK: initialized KG store at {db_path} with {triple_count} rdfs:subClassOf triples."
        )


@kg_group.command("snapshot")
@db_path_ro_option()
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path(".cataforge/kg/snapshots"),
    show_default=True,
    help="Directory to write the snapshot NQuads file and metadata.",
)
@click.option(
    "--label",
    default=None,
    help="Optional label appended to the snapshot filename.",
)
@click.pass_context
def kg_snapshot(
    ctx: click.Context, db_path: Path, output_dir: Path, label: str | None
) -> None:
    """Save a full snapshot of the current KG store."""
    db_path = root_relative_default(ctx, "db_path", db_path, rel=KG_STORE_REL)
    output_dir = root_relative_default(
        ctx, "output_dir", output_dir, rel=Path(".cataforge/kg/snapshots")
    )

    from cataforge.domain.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraph
    from cataforge.domain.kg.snapshot import create_snapshot

    config = KGConfig(store_backend="oxigraph", db_path=db_path)
    try:
        with KnowledgeGraph.connect(config) as kg:
            meta = create_snapshot(kg.store, config, output_dir, label=label)
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    click.echo(f"OK: snapshot saved to {meta.path} ({meta.quad_count} quads)")


@kg_group.command("rollback")
@click.argument(
    "snapshot_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@db_path_option()
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite the existing store without confirmation.",
)
@click.pass_context
def kg_rollback(
    ctx: click.Context, snapshot_path: Path, db_path: Path, force: bool
) -> None:
    """Restore the KG store from a snapshot file.

    SNAPSHOT_PATH is the path to the .nq file created by `cataforge kg snapshot`.
    """
    db_path = root_relative_default(ctx, "db_path", db_path, rel=KG_STORE_REL)

    from cataforge.domain.kg import KGConfig, KGStoreAlreadyExistsError
    from cataforge.domain.kg.snapshot import restore_snapshot

    if not force:
        click.confirm(
            f"This will replace the store at {db_path}. Continue?",
            abort=True,
        )

    config = KGConfig(store_backend="oxigraph", db_path=db_path)
    try:
        count = restore_snapshot(snapshot_path, config, force=True)
    except KGStoreAlreadyExistsError as exc:
        raise KGStoreError(str(exc)) from exc

    click.echo(f"OK: restored {count} quads from {snapshot_path}")


@kg_group.command("repair")
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing docs/ and .cataforge/.",
)
@db_path_ro_option()
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Report what would be repaired without modifying the store.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit a JSON stats blob instead of the human-readable summary.",
)
@click.pass_context
def kg_repair(
    ctx: click.Context,
    project_root: Path,
    db_path: Path,
    dry_run: bool,
    json_output: bool,
) -> None:
    """Auto-fix KG drift detected by reconcile."""
    from cataforge.domain.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraph
    from cataforge.domain.kg._dispatch import kg_config_for
    from cataforge.domain.kg.repair import repair

    project_root = root_relative_default(ctx, "project_root", project_root)
    db_path = root_relative_default(ctx, "db_path", db_path, rel=KG_STORE_REL)
    project_root = project_root.resolve()
    base_config = kg_config_for(project_root)

    config = KGConfig(
        store_backend="oxigraph",
        db_path=db_path,
        kg_active_doc_types=set(base_config.kg_active_doc_types),
        ontology_namespace=base_config.ontology_namespace,
        base_namespace=base_config.base_namespace,
    )

    try:
        with KnowledgeGraph.connect(config) as kg:
            stats = repair(kg.store, project_root, config, dry_run=dry_run)
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    if json_output:
        click.echo(
            json.dumps(
                {
                    "dry_run": dry_run,
                    "ghosts_removed": stats.ghosts_removed,
                    "missing_ingested": stats.missing_ingested,
                    "errors": stats.errors,
                },
                indent=2,
            )
        )
    else:
        prefix = "[dry-run] " if dry_run else ""
        click.echo(
            f"{prefix}ghosts_removed={stats.ghosts_removed} "
            f"missing_ingested={stats.missing_ingested}"
        )
        for err in stats.errors:
            click.echo(f"  ERROR: {err}", err=True)

    if stats.errors:
        raise KGVerificationError(f"repair encountered {len(stats.errors)} error(s)")


@kg_group.command("diff")
@click.argument(
    "snapshot_a",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.argument(
    "snapshot_b",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit the diff as a JSON blob instead of the grouped summary.",
)
@click.pass_context
def kg_diff(
    ctx: click.Context,
    snapshot_a: Path,
    snapshot_b: Path,
    json_output: bool,
) -> None:
    """Show the entity/relation delta between two snapshot files.

    SNAPSHOT_A and SNAPSHOT_B are `.nq` files created by `cataforge kg
    snapshot`. The diff is computed from A to B at the entity level
    (added / removed / content-modified) and the traceability-relation
    level (added / removed). Exits non-zero when the snapshots differ.
    """
    from cataforge.domain.kg.diff import diff_snapshots, render_diff_json, render_diff_text

    diff = diff_snapshots(snapshot_a, snapshot_b)
    click.echo(render_diff_json(diff) if json_output else render_diff_text(diff))

    if not diff.ok:
        ctx.exit(1)


# ------------------------------------------------------------------
# kg query
# ------------------------------------------------------------------
