"""cataforge kg — knowledge graph store lifecycle.

Subcommand build-out tracks the alpha sub-PR sequence in task-7 §7.1:

* sub-PR 2 — `init`
* sub-PR 3 — `import`, `validate`
* sub-PR 4 — `export`
* sub-PR 6 — `reconcile`, `compare-read` (this file)
* later — `repair`, `snapshot`, `rollback`, `diff`
"""
from __future__ import annotations

import json
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
        "Restrict to specific doc_types. Repeatable. Default = Alpha scope "
        "(prd, arch, test-report) per task-7 §7.1."
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
    """Ingest business documents into the KG (task-7 §7.2 six-phase pipeline)."""
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
            err = CataforgeError(
                f"{exc}\nHint: run `cataforge kg init` before `kg import`."
            )
            err.exit_code = 1
            raise err from exc

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
        err = CataforgeError("KG import verification failed.")
        err.exit_code = 3
        raise err


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
        err = CataforgeError(str(exc))
        err.exit_code = 1
        raise err from exc

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
        err = CataforgeError("validation reported violations.")
        err.exit_code = 3
        raise err


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
    """Export the KG to per-entity Markdown files (task-4 pipeline)."""
    from cataforge.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraphStore
    from cataforge.kg.export import compile_to_markdown

    config = KGConfig(store_backend="oxigraph", db_path=db_path)
    try:
        with KnowledgeGraphStore.connect(config) as handle:
            result = compile_to_markdown(handle.raw, output_dir)
    except KGStoreNotInitializedError as exc:
        err = CataforgeError(str(exc))
        err.exit_code = 1
        raise err from exc

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
        err = CataforgeError(f"{len(result.errors)} export errors")
        err.exit_code = 3
        raise err


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
    `missing` or `ghost` entry exists. Used at Alpha exit to certify
    that doctor's ERROR-gate cycle has nothing to flag, and
    operationally to spot drift after every `cataforge kg commit`.
    """
    from cataforge.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraphStore
    from cataforge.kg._dispatch import kg_config_for
    from cataforge.kg.reconcile import reconcile, write_report

    project_root = project_root.resolve()
    base_config = kg_config_for(project_root)

    if doc_types:
        active = set(doc_types)
    else:
        active = set(base_config.kg_active_doc_types)

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
        err = CataforgeError(str(exc))
        err.exit_code = 1
        raise err from exc

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
        err = CataforgeError(
            f"reconcile reported {report.overall_divergence_count} divergence(s); "
            f"see {output_path}"
        )
        err.exit_code = 3
        raise err


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
        "Reserved for forward-compat with §7.5; content_hash compare is "
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

    Per task-7 §7.5, this is a *diagnostic* check, not a gate: alarms
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

    if doc_types:
        active = set(doc_types)
    else:
        active = set(base_config.kg_active_doc_types)

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
        err = CataforgeError(str(exc))
        err.exit_code = 1
        raise err from exc

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
