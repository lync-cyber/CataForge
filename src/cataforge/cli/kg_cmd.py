"""cataforge kg — knowledge graph store lifecycle.

Subcommands: init, import, validate, export, reconcile, compare-read,
snapshot, rollback, repair, query, trace.
"""
from __future__ import annotations

import json
from pathlib import Path

import click

from cataforge.cli.errors import CataforgeError, KGStoreError, KGVerificationError
from cataforge.cli.main import cli


@cli.group("kg")
def kg_group() -> None:
    """Knowledge graph store management."""


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
    lack of RDFS entailment — without them, queries like
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
            f"OK: initialized KG store at {db_path} with {triple_count} "
            f"rdfs:subClassOf triples."
        )


@kg_group.command("import")
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing docs/ and .cataforge/.",
)
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
    help="Store backend. `memory` is for tests and dry-runs only.",
)
@click.option(
    "--doc-type",
    "doc_types",
    multiple=True,
    help=(
        "Restrict to specific doc_types. Repeatable. "
        "Default = prd, arch, test-report."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Run phases 1–4 + 6 against the existing graph; skip phase 5 write.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit a JSON stats blob instead of the human-readable table.",
)
def kg_import(
    project_root: Path,
    db_path: Path,
    backend: str,
    doc_types: tuple[str, ...],
    dry_run: bool,
    json_output: bool,
) -> None:
    """Ingest business documents into the KG (six-phase pipeline)."""
    from cataforge.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraphStore
    from cataforge.kg.ingest import DEFAULT_DOC_TYPES, run_migration

    config = KGConfig(
        store_backend=backend,  # type: ignore[arg-type]
        db_path=db_path,
    )

    types = doc_types if doc_types else DEFAULT_DOC_TYPES

    if backend == "memory":
        from cataforge.kg.store import init_store

        handle = init_store(config, force=True)
    else:
        try:
            handle = KnowledgeGraphStore.connect(config).__enter__()
        except KGStoreNotInitializedError as exc:
            raise KGStoreError(
                f"{exc}\nHint: run `cataforge kg init` before `kg import`."
            ) from exc

    try:
        stats, _entities, _relations = run_migration(
            handle.raw,
            project_root,
            config,
            doc_types=tuple(types),
            dry_run=dry_run,
        )
    finally:
        handle.close()

    if json_output:
        click.echo(json.dumps(stats.to_dict(), indent=2, sort_keys=True))
    else:
        prefix = "[DRY-RUN] " if dry_run else ""
        click.echo(
            f"{prefix}docs={stats.parsed_docs} "
            f"entities={stats.extracted_entities} "
            f"relations={stats.extracted_relations}"
        )
        click.echo(
            f"  written={stats.write_stats.entities_written}"
            f"+{stats.write_stats.relations_written} "
            f"skipped={stats.write_stats.entities_skipped}"
            f"+{stats.write_stats.relations_skipped}"
        )
        if stats.verify_result is not None:
            click.echo(
                f"  verify: ok={stats.verify_result.ok} "
                f"missing={len(stats.verify_result.missing_entities)} "
                f"hash_mismatch={len(stats.verify_result.content_hash_mismatches)}"
            )

    if stats.verify_result is not None and not stats.verify_result.ok and not dry_run:
        raise KGVerificationError("KG import verification failed.")


@kg_group.command("validate")
@click.option(
    "--db-path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path(".cataforge/kg/store"),
    show_default=True,
    help="Filesystem path of the RocksDB-backed Oxigraph store.",
)
@click.option(
    "--shacl/--no-shacl",
    default=False,
    help=(
        "Run SHACL shapes from `_generated/core_shapes.ttl` against the live "
        "graph. Requires pyshacl + rdflib (extra); silently skipped if absent."
    ),
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit a JSON report instead of the table.",
)
def kg_validate(db_path: Path, shacl: bool, json_output: bool) -> None:
    """Check the live KG for orphan nodes and broken traceability edges."""
    from cataforge.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraphStore
    from cataforge.kg.validate import validate

    config = KGConfig(store_backend="oxigraph", db_path=db_path)
    try:
        with KnowledgeGraphStore.connect(config) as handle:
            report = validate(handle.raw, config, run_shacl=shacl)
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    if json_output:
        click.echo(
            json.dumps(
                {
                    "ok": report.ok,
                    "shacl_skipped": report.shacl_skipped,
                    "violations": [
                        {
                            "severity": v.severity,
                            "entity_id": v.entity_id,
                            "shape": v.shape,
                            "message": v.message,
                        }
                        for v in report.violations
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        if not report.violations:
            click.echo("OK: no violations")
        else:
            click.echo(
                f"{'Severity':<12} {'Entity':<20} {'Shape':<28} Message"
            )
            click.echo("-" * 80)
            for v in report.violations:
                click.echo(
                    f"{v.severity:<12} {v.entity_id:<20} {v.shape:<28} {v.message}"
                )
        if report.shacl_skipped and shacl:
            click.echo(
                "Note: SHACL pass skipped (pyshacl/rdflib not installed "
                "or shapes file missing)."
            )

    if not report.ok:
        raise KGVerificationError("validation reported violations.")


@kg_group.command("export")
@click.option(
    "--db-path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path(".cataforge/kg/store"),
    show_default=True,
    help="Filesystem path of the RocksDB-backed Oxigraph store.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("docs"),
    show_default=True,
    help="Root directory for the exported Markdown tree.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit a JSON result blob (per-file sha256 included) instead of the table.",
)
def kg_export(db_path: Path, output_dir: Path, json_output: bool) -> None:
    """Export the KG to per-entity Markdown files."""
    from cataforge.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraphStore
    from cataforge.kg.export import compile_to_markdown

    config = KGConfig(store_backend="oxigraph", db_path=db_path)
    try:
        with KnowledgeGraphStore.connect(config) as handle:
            result = compile_to_markdown(handle.raw, output_dir)
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    if json_output:
        click.echo(
            json.dumps(
                {
                    "entity_count": result.entity_count,
                    "rendered": len(result.file_records),
                    "errors": [
                        {"entity_id": e, "message": m} for e, m in result.errors
                    ],
                    "files": result.file_hashes,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        click.echo(
            f"OK: rendered {len(result.file_records)}/{result.entity_count} entities "
            f"→ {result.output_dir}"
        )
        if result.errors:
            click.echo(f"  errors: {len(result.errors)}")
            for eid, msg in result.errors:
                click.echo(f"   - {eid}: {msg}")

    if result.errors:
        raise KGVerificationError(f"{len(result.errors)} export errors")


@kg_group.command("reconcile")
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing docs/ and .cataforge/.",
)
@click.option(
    "--db-path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=Path(".cataforge/kg/store"),
    show_default=True,
    help="Filesystem path of the RocksDB-backed Oxigraph store.",
)
@click.option(
    "--doc-type",
    "doc_types",
    multiple=True,
    help=(
        "Restrict to specific doc_types. Repeatable. Default = the project's "
        "kg_active_doc_types (framework.json kg.kg_active_doc_types, "
        "fall-back: prd, arch, test)."
    ),
)
@click.option(
    "--report-output",
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help=(
        "Path to write the JSON report. "
        "Default = <project-root>/docs/.kg-reconcile-report.json."
    ),
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Also emit the report to stdout as JSON.",
)
def kg_reconcile(
    project_root: Path,
    db_path: Path,
    doc_types: tuple[str, ...],
    report_output: Path | None,
    json_output: bool,
) -> None:
    """Detect drift between Markdown sources and the KG store (per doc_type).

    For each active doc_type, compares FS-extracted entities and
    traceability triples against what is in the KG. Writes the diff to
    `docs/.kg-reconcile-report.json` and exits non-zero if any
    `missing` or `ghost` entry exists. Operationally used to spot
    drift after every `cataforge kg import`.
    """
    from cataforge.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraphStore
    from cataforge.kg._dispatch import kg_config_for
    from cataforge.kg.reconcile import reconcile, write_report

    project_root = project_root.resolve()
    base_config = kg_config_for(project_root)

    active = (
        set(doc_types) if doc_types else set(base_config.kg_active_doc_types)
    )

    if not active:
        click.echo(
            "  (no active doc_types — nothing to reconcile; "
            "set kg.kg_active_doc_types in framework.json)"
        )
        return

    config = KGConfig(
        store_backend="oxigraph",
        db_path=db_path,
        kg_active_doc_types=active,
        ontology_namespace=base_config.ontology_namespace,
        base_namespace=base_config.base_namespace,
    )

    try:
        with KnowledgeGraphStore.connect(config) as handle:
            report = reconcile(handle.raw, project_root, config)
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    output_path = (
        report_output
        if report_output is not None
        else project_root / "docs" / ".kg-reconcile-report.json"
    )
    write_report(report, output_path)

    if json_output:
        click.echo(
            json.dumps(
                report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False
            )
        )
    else:
        click.echo(
            f"reconcile: divergence={report.overall_divergence_count} "
            f"doc_types={sorted(active)}"
        )
        for dt, per in sorted(report.per_doc_type.items()):
            marker = "OK" if per.divergence_count == 0 else "DRIFT"
            click.echo(
                f"  [{marker}] {dt}: "
                f"missing_entities={len(per.missing_entities)} "
                f"ghost_entities={len(per.ghost_entities)} "
                f"missing_relations={len(per.missing_relations)} "
                f"ghost_relations={len(per.ghost_relations)}"
            )
            if per.missing_entities:
                preview = per.missing_entities[:5]
                ellipsis = "..." if len(per.missing_entities) > 5 else ""
                click.echo(
                    f"        missing_entities: {preview}{ellipsis}"
                )
            if per.ghost_entities:
                preview = per.ghost_entities[:5]
                ellipsis = "..." if len(per.ghost_entities) > 5 else ""
                click.echo(
                    f"        ghost_entities: {preview}{ellipsis}"
                )
        click.echo(f"  report: {output_path}")

    if not report.ok:
        raise KGVerificationError(
            f"reconcile reported {report.overall_divergence_count} divergence(s); "
            f"see {output_path}"
        )


@kg_group.command("compare-read")
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing docs/ and .cataforge/.",
)
@click.option(
    "--db-path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=Path(".cataforge/kg/store"),
    show_default=True,
    help="Filesystem path of the RocksDB-backed Oxigraph store.",
)
@click.option(
    "--doc-type",
    "doc_types",
    multiple=True,
    help=(
        "Restrict the sample to specific doc_types. Repeatable. "
        "Default = the project's kg_active_doc_types."
    ),
)
@click.option(
    "--sample-size",
    type=int,
    default=20,
    show_default=True,
    help="How many random entities to sample. The audit walks every "
    "entity when the population is smaller than this.",
)
@click.option(
    "--threshold",
    type=float,
    default=1.0,
    show_default=True,
    help=(
        "Reserved for forward-compat; content_hash compare is "
        "binary so this value is currently ignored."
    ),
)
@click.option(
    "--seed",
    type=int,
    default=None,
    help="Optional RNG seed; pin to get a reproducible sample.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit a JSON audit report instead of the table.",
)
def kg_compare_read(
    project_root: Path,
    db_path: Path,
    doc_types: tuple[str, ...],
    sample_size: int,
    threshold: float,
    seed: int | None,
    json_output: bool,
) -> None:
    """Sample-audit KG-rendered entities against the legacy file slice.

    This is a *diagnostic* check, not a gate: alarms
    do not block writes. Operators run it periodically post-cutover; if
    alarms persist for a doc_type the prescribed response is to remove
    that doc_type from `kg_active_doc_types` and investigate. Exit code
    is always 0 (success) unless the run itself fails.
    """
    from cataforge.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraph
    from cataforge.kg._dispatch import kg_config_for
    from cataforge.kg.compare_read import (
        compare_read,
    )

    project_root = project_root.resolve()
    base_config = kg_config_for(project_root)

    active = (
        set(doc_types) if doc_types else set(base_config.kg_active_doc_types)
    )

    if not active:
        click.echo("  (no active doc_types — nothing to audit)")
        return

    config = KGConfig(
        store_backend="oxigraph",
        db_path=db_path,
        kg_active_doc_types=active,
        ontology_namespace=base_config.ontology_namespace,
        base_namespace=base_config.base_namespace,
    )

    try:
        with KnowledgeGraph.connect(config) as kg:
            report = compare_read(
                kg,
                project_root,
                doc_types=active,
                sample_size=sample_size,
                threshold=threshold,
                seed=seed,
            )
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    if json_output:
        click.echo(
            json.dumps(
                report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False
            )
        )
        return

    click.echo(
        f"compare-read: sampled={report.sampled_count} "
        f"alarms={len(report.alarms)}"
    )
    if not report.alarms:
        click.echo("  OK (every sampled entity's content_hash matches KG)")
        return
    for alarm in report.alarms[:10]:
        click.echo(
            f"  ALARM {alarm.entity_id} ({alarm.doc_type}): "
            f"{alarm.reason}"
        )
    if len(report.alarms) > 10:
        click.echo(f"  ... +{len(report.alarms) - 10} more")


@kg_group.command("snapshot")
@click.option(
    "--db-path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=Path(".cataforge/kg/store"),
    show_default=True,
    help="Filesystem path of the RocksDB-backed Oxigraph store.",
)
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
def kg_snapshot(db_path: Path, output_dir: Path, label: str | None) -> None:
    """Save a full snapshot of the current KG store."""
    from cataforge.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraphStore
    from cataforge.kg.snapshot import create_snapshot

    config = KGConfig(store_backend="oxigraph", db_path=db_path)
    try:
        with KnowledgeGraphStore.connect(config) as handle:
            meta = create_snapshot(
                handle.raw, config, output_dir, label=label
            )
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    click.echo(
        f"OK: snapshot saved to {meta.path} ({meta.quad_count} quads)"
    )


@kg_group.command("rollback")
@click.argument(
    "snapshot_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--db-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path(".cataforge/kg/store"),
    show_default=True,
    help="Filesystem path of the RocksDB-backed Oxigraph store to replace.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite the existing store without confirmation.",
)
def kg_rollback(snapshot_path: Path, db_path: Path, force: bool) -> None:
    """Restore the KG store from a snapshot file.

    SNAPSHOT_PATH is the path to the .nq file created by `cataforge kg snapshot`.
    """
    from cataforge.kg import KGConfig, KGStoreAlreadyExistsError
    from cataforge.kg.snapshot import restore_snapshot

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
@click.option(
    "--db-path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=Path(".cataforge/kg/store"),
    show_default=True,
    help="Filesystem path of the RocksDB-backed Oxigraph store.",
)
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
    from cataforge.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraphStore
    from cataforge.kg._dispatch import kg_config_for
    from cataforge.kg.repair import repair

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
        with KnowledgeGraphStore.connect(config) as handle:
            stats = repair(
                handle.raw, project_root, config, dry_run=dry_run
            )
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    if json_output:
        import json as json_mod  # noqa: PLC0415

        click.echo(
            json_mod.dumps(
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
        ctx.exit(1)


# ------------------------------------------------------------------
# kg query
# ------------------------------------------------------------------

@kg_group.command("query")
@click.argument("query_or_file")
@click.option(
    "--db-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path(".cataforge/kg/store"),
    show_default=True,
    help="Filesystem path of the RocksDB-backed Oxigraph store.",
)
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["table", "json", "turtle"]),
    default="table",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--limit",
    type=int,
    default=100,
    show_default=True,
    help="Maximum rows for SELECT results.",
)
@click.option(
    "--timeout",
    type=float,
    default=30.0,
    show_default=True,
    help="Query timeout in seconds.",
)
def kg_query(
    query_or_file: str,
    db_path: Path,
    output_fmt: str,
    limit: int,
    timeout: float,
) -> None:
    """Execute a SPARQL query against the KG store.

    QUERY_OR_FILE is a SPARQL string or a path to a .sparql file.
    """
    from cataforge.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraphStore

    sparql = _resolve_sparql_input(query_or_file)
    sparql = _inject_limit(sparql, limit)

    config = KGConfig(store_backend="oxigraph", db_path=db_path)
    try:
        with KnowledgeGraphStore.connect(config) as handle:
            try:
                raw_result = handle.raw.query(sparql)
            except Exception as exc:
                raise CataforgeError(f"SPARQL error: {exc}") from exc
            _format_query_result(raw_result, output_fmt)
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc


def _resolve_sparql_input(query_or_file: str) -> str:
    p = Path(query_or_file)
    if p.suffix == ".sparql" and p.is_file():
        return p.read_text(encoding="utf-8").strip()
    if p.is_file():
        return p.read_text(encoding="utf-8").strip()
    return query_or_file


def _inject_limit(sparql: str, limit: int) -> str:
    upper = sparql.upper()
    if "SELECT" in upper and "LIMIT" not in upper:
        return f"{sparql.rstrip().rstrip(';')} LIMIT {limit}"
    return sparql


def _format_query_result(result: object, fmt: str) -> None:
    result_type = type(result).__name__

    if result_type == "QueryBoolean" or isinstance(result, bool):
        _format_ask_result(result, fmt)
    elif result_type == "QuerySolutions":
        _format_select_result(result, fmt)
    elif result_type == "QueryTriples":
        _format_construct_result(result, fmt)
    else:
        _format_select_result(result, fmt)


def _format_ask_result(result: object, fmt: str) -> None:
    value = bool(result)
    if fmt == "json":
        click.echo(json.dumps({"result": value}))
    else:
        click.echo("true" if value else "false")


def _format_select_result(result: object, fmt: str) -> None:
    if hasattr(result, "variables"):
        raw_vars = list(result.variables)  # type: ignore[union-attr]
        variables = [str(v).lstrip("?") for v in raw_vars]
    else:
        raw_vars = []
        variables = []

    rows_data: list[dict[str, str]] = []
    for row in result:  # type: ignore[arg-type]
        record: dict[str, str] = {}
        for raw_var, name in zip(raw_vars, variables, strict=True):
            try:
                val = row[raw_var]
            except (KeyError, IndexError):
                val = None
            record[name] = _term_to_str(val)
        rows_data.append(record)

    if fmt == "json":
        click.echo(json.dumps(rows_data, indent=2, ensure_ascii=False))
        return

    if not rows_data:
        click.echo("(no results)")
        return

    col_widths = {v: len(v) for v in variables}
    for row in rows_data:
        for v in variables:
            col_widths[v] = max(col_widths[v], len(row.get(v, "")))

    header = "  ".join(v.ljust(col_widths[v]) for v in variables)
    separator = "  ".join("-" * col_widths[v] for v in variables)
    click.echo(header)
    click.echo(separator)
    for row in rows_data:
        line = "  ".join(row.get(v, "").ljust(col_widths[v]) for v in variables)
        click.echo(line)


def _format_construct_result(result: object, fmt: str) -> None:
    triples = list(result)  # type: ignore[arg-type]

    if fmt == "json":
        out = [
            {
                "subject": _term_to_str(t.subject),
                "predicate": _term_to_str(t.predicate),
                "object": _term_to_str(t.object),
            }
            for t in triples
        ]
        click.echo(json.dumps(out, indent=2, ensure_ascii=False))
        return

    if fmt == "turtle":
        for t in triples:
            s = _ntriples_term(t.subject)
            p = _ntriples_term(t.predicate)
            o = _ntriples_term(t.object)
            click.echo(f"{s} {p} {o} .")
        return

    col_widths = {"subject": 7, "predicate": 9, "object": 6}
    rows = []
    for t in triples:
        row = {
            "subject": _term_to_str(t.subject),
            "predicate": _term_to_str(t.predicate),
            "object": _term_to_str(t.object),
        }
        for k in col_widths:
            col_widths[k] = max(col_widths[k], len(row[k]))
        rows.append(row)

    header = "  ".join(k.ljust(col_widths[k]) for k in ("subject", "predicate", "object"))
    separator = "  ".join("-" * col_widths[k] for k in ("subject", "predicate", "object"))
    click.echo(header)
    click.echo(separator)
    for row in rows:
        line = "  ".join(row[k].ljust(col_widths[k]) for k in ("subject", "predicate", "object"))
        click.echo(line)


def _term_to_str(term: object) -> str:
    if term is None:
        return ""
    return str(getattr(term, "value", term))


def _ntriples_term(term: object) -> str:
    if term is None:
        return '""'
    type_name = type(term).__name__
    if type_name == "NamedNode":
        return f"<{term.value}>"  # type: ignore[union-attr]
    if type_name == "Literal":
        escaped = term.value.replace("\\", "\\\\").replace('"', '\\"')  # type: ignore[union-attr]
        return f'"{escaped}"'
    if type_name == "BlankNode":
        return f"_:{term.value}"  # type: ignore[union-attr]
    return f"<{term}>"


# ------------------------------------------------------------------
# kg trace
# ------------------------------------------------------------------

@kg_group.command("trace")
@click.argument("entity_id", required=False, default=None)
@click.option(
    "--db-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=Path(".cataforge/kg/store"),
    show_default=True,
    help="Filesystem path of the RocksDB-backed Oxigraph store.",
)
@click.option(
    "--direction",
    type=click.Choice(["downstream", "upstream", "both"]),
    default="downstream",
    show_default=True,
    help="Chain traversal direction.",
)
@click.option(
    "--coverage",
    is_flag=True,
    default=False,
    help=(
        "Without ENTITY_ID: show the global Feature coverage matrix. "
        "With ENTITY_ID: append coverage detail to the trace chain."
    ),
)
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["table", "json", "mermaid"]),
    default="table",
    show_default=True,
    help="Output format.",
)
def kg_trace(
    entity_id: str | None,
    db_path: Path,
    direction: str,
    coverage: bool,
    output_fmt: str,
) -> None:
    """Trace the dependency chain from a business entity.

    When called with --coverage and no ENTITY_ID, prints a global
    Feature coverage matrix instead of a single-entity chain.
    """
    from cataforge.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraph

    config = KGConfig(store_backend="oxigraph", db_path=db_path)

    if coverage and entity_id is None:
        try:
            with KnowledgeGraph.connect(config) as kg:
                _coverage_matrix(kg, output_fmt)
        except KGStoreNotInitializedError as exc:
            raise KGStoreError(str(exc)) from exc
        return

    if entity_id is None:
        raise CataforgeError("ENTITY_ID is required (or use --coverage for global matrix).")

    try:
        with KnowledgeGraph.connect(config) as kg:
            if not kg.query.exists(entity_id):
                raise CataforgeError(f"Entity not found: {entity_id}")

            chain = kg.trace.from_requirement(entity_id, direction=direction)  # type: ignore[arg-type]

            coverage_detail = None
            if coverage:
                coverage_detail = kg.trace.coverage(entity_id)

            if output_fmt == "json":
                _trace_json(chain, coverage_detail)
            elif output_fmt == "mermaid":
                _trace_mermaid(chain, kg)
            else:
                _trace_table(chain, kg, coverage_detail)
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc


def _coverage_matrix(kg: object, fmt: str) -> None:
    from cataforge.kg import KnowledgeGraph

    assert isinstance(kg, KnowledgeGraph)
    rows = kg.trace.bidirectional_coverage()

    if fmt == "json":
        out = [
            {
                "feature_id": r.feature_id,
                "title": r.title,
                "has_impl": r.has_impl,
                "has_test": r.has_test,
            }
            for r in rows
        ]
        click.echo(json.dumps(out, indent=2, ensure_ascii=False))
        return

    if not rows:
        click.echo("(no features found)")
        return

    id_w = max(len("Feature"), max(len(r.feature_id) for r in rows))
    title_w = max(len("Title"), max(len(r.title or "") for r in rows))
    click.echo(
        f"{'Feature':<{id_w}}  {'Title':<{title_w}}  Impl?  Test?"
    )
    click.echo(
        f"{'-' * id_w}  {'-' * title_w}  -----  -----"
    )
    for r in rows:
        impl = "yes" if r.has_impl else "no"
        test = "yes" if r.has_test else "no"
        click.echo(
            f"{r.feature_id:<{id_w}}  {(r.title or ''):<{title_w}}  "
            f"{impl:<5}  {test:<5}"
        )


def _trace_json(chain: object, coverage_detail: dict | None) -> None:
    import dataclasses

    d = dataclasses.asdict(chain)  # type: ignore[arg-type]
    if coverage_detail is not None:
        d["coverage_detail"] = coverage_detail
    click.echo(json.dumps(d, indent=2, ensure_ascii=False))


def _chain_buckets(chain: object):  # noqa: ANN201
    from cataforge.kg.trace import TraceChain

    assert isinstance(chain, TraceChain)
    return [
        ("requirements", chain.requirements),
        ("acceptance_criteria", chain.acceptance_criteria),
        ("modules", chain.modules),
        ("components", chain.components),
        ("tasks", chain.tasks),
        ("test_cases", chain.test_cases),
        ("review_reports", chain.review_reports),
    ]


def _trace_table(chain: object, kg: object, coverage_detail: dict | None) -> None:
    from cataforge.kg import KnowledgeGraph
    from cataforge.kg.trace import TraceChain

    assert isinstance(chain, TraceChain)
    assert isinstance(kg, KnowledgeGraph)

    click.echo(f"Traceability chain from {chain.root_id} (coverage={chain.coverage_status})")
    click.echo()

    buckets = _chain_buckets(chain)
    layer_w = max(len("Layer"), max((len(b[0]) for b in buckets), default=5))
    click.echo(f"{'Layer':<{layer_w}}  {'Entity ID':<12}  Title")
    click.echo(f"{'-' * layer_w}  {'-' * 12}  {'-' * 30}")

    root_entity = kg.query.entity(chain.root_id)
    root_title = root_entity.get("title", "") if root_entity else ""
    root_class = root_entity.get("_class", "root") if root_entity else "root"
    click.echo(f"{root_class:<{layer_w}}  {chain.root_id:<12}  {root_title}")

    for layer_name, ids in buckets:
        for eid in ids:
            if eid == chain.root_id:
                continue
            entity = kg.query.entity(eid)
            title = entity.get("title", "") if entity else ""
            click.echo(f"{layer_name:<{layer_w}}  {eid:<12}  {title}")

    if coverage_detail:
        click.echo()
        status = coverage_detail.get("status", "unknown")
        impl = "yes" if coverage_detail.get("has_impl") else "no"
        test = "yes" if coverage_detail.get("has_test") else "no"
        click.echo(f"Coverage: status={status} impl={impl} test={test}")


def _trace_mermaid(chain: object, kg: object) -> None:
    from cataforge.kg import KnowledgeGraph
    from cataforge.kg.trace import TraceChain

    assert isinstance(chain, TraceChain)
    assert isinstance(kg, KnowledgeGraph)

    click.echo("graph TD")

    buckets = _chain_buckets(chain)

    all_ids: list[str] = [chain.root_id]
    seen = {chain.root_id}
    for _, ids in buckets:
        for eid in ids:
            if eid not in seen:
                all_ids.append(eid)
                seen.add(eid)

    for eid in all_ids:
        entity = kg.query.entity(eid)
        title = entity.get("title", "") if entity else ""
        safe_label = title.replace('"', "'")
        click.echo(f'    {eid}["{eid}: {safe_label}"]')

    bucket_map = {name: ids for name, ids in buckets}
    for src_layer, dst_layer, rel in _MERMAID_EDGE_MAP:
        src_ids = bucket_map.get(src_layer, [])
        dst_ids = bucket_map.get(dst_layer, [])
        if src_ids and dst_ids:
            for s in src_ids:
                for d in dst_ids:
                    click.echo(f"    {s} -->|{rel}| {d}")

    downstream_ids = [eid for eid in all_ids if eid != chain.root_id]
    if downstream_ids and not any(
        bucket_map.get(src) and bucket_map.get(dst)
        for src, dst, _ in _MERMAID_EDGE_MAP
    ):
        for d in downstream_ids:
            click.echo(f"    {chain.root_id} --> {d}")


_MERMAID_EDGE_MAP = [
    ("requirements", "modules", "implements"),
    ("requirements", "components", "implements"),
    ("modules", "tasks", "decomposes"),
    ("acceptance_criteria", "test_cases", "verifies"),
    ("requirements", "acceptance_criteria", "validates"),
]
