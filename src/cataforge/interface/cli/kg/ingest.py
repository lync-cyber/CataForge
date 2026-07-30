"""cataforge kg ingestion & consistency — import, export, validate, drift-check, compare-read."""

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
from cataforge.interface.cli._support._hints import NO_RELATIONS_HINT
from cataforge.interface.cli._support.helpers import root_relative_default
from cataforge.interface.cli.kg import kg_group
from cataforge.interface.cli.kg._options import db_path_option, db_path_ro_option


@kg_group.command("import", hidden=True)
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing docs/ and .cataforge/.",
)
@db_path_option()
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
        "Restrict to specific doc_types. Repeatable. Default = the project's "
        "framework.json kg_active_doc_types (falls back to the built-in "
        "business doc_type set when unset), so import scope matches the doctor "
        "kg_ingestion_completeness gate."
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
@click.pass_context
def kg_import(
    ctx: click.Context,
    project_root: Path,
    db_path: Path,
    backend: str,
    doc_types: tuple[str, ...],
    dry_run: bool,
    json_output: bool,
) -> None:
    """Low-level KG ingest (six-phase pipeline). Business flows use ``context ingest``."""
    project_root = root_relative_default(ctx, "project_root", project_root)
    db_path = root_relative_default(ctx, "db_path", db_path, rel=KG_STORE_REL)

    from cataforge.domain.kg import (
        KGConfig,
        KGEntityCollisionError,
        KGStoreNotInitializedError,
        KnowledgeGraph,
    )
    from cataforge.domain.kg._dispatch import active_doc_types, kg_enabled
    from cataforge.domain.kg.ingest import DEFAULT_DOC_TYPES, run_migration

    config = KGConfig(
        store_backend=backend,  # type: ignore[arg-type]
        db_path=db_path,
    )

    import contextlib  # noqa: PLC0415

    # Default scope = the project's active doc_types, so a plain `kg import`
    # ingests exactly what the doctor `kg_ingestion_completeness` gate checks.
    # Fall back to the built-in business set when none are declared.
    if doc_types:
        types: tuple[str, ...] = doc_types
    elif not kg_enabled(project_root):
        click.echo(
            "markdown mode (context.mode): KG disabled — nothing to import. "
            "Pass --doc-type to override."
        )
        return
    else:
        active = active_doc_types(project_root)
        types = tuple(sorted(active)) if active else tuple(DEFAULT_DOC_TYPES)

    try:
        if backend == "memory":
            from cataforge.domain.kg import init_store  # noqa: PLC0415

            handle = init_store(config, force=True)
            with contextlib.closing(handle):
                stats, _entities, _relations = run_migration(
                    handle.raw,
                    project_root,
                    config,
                    doc_types=tuple(types),
                    dry_run=dry_run,
                )
        else:
            with KnowledgeGraph.connect(config) as kg:
                stats, _entities, _relations = run_migration(
                    kg.store,
                    project_root,
                    config,
                    doc_types=tuple(types),
                    dry_run=dry_run,
                )
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(f"{exc}\nHint: run `cataforge kg init` before `kg import`.") from exc
    except KGEntityCollisionError as exc:
        raise KGVerificationError(str(exc)) from exc

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
        if stats.extracted_relations == 0 and stats.extracted_entities > 0:
            click.echo(f"  ({NO_RELATIONS_HINT})")
        if stats.verify_result is not None:
            click.echo(
                f"  verify: ok={stats.verify_result.ok} "
                f"missing={len(stats.verify_result.missing_entities)} "
                f"hash_mismatch={len(stats.verify_result.content_hash_mismatches)}"
            )

    if stats.verify_result is not None and not stats.verify_result.ok and not dry_run:
        raise KGVerificationError("KG import verification failed.")


@kg_group.command("validate")
@db_path_ro_option()
@click.option(
    "--shacl/--no-shacl",
    default=False,
    help=(
        "Run SHACL shapes from `_generated/core_shapes.ttl` against the live "
        "graph. Requires pyshacl + rdflib (extra); skipped with a note if absent."
    ),
)
@click.option(
    "--require-shacl",
    is_flag=True,
    default=False,
    help=(
        "Fail (exit non-zero) when the SHACL pass cannot run — deps or shapes "
        "missing. Implies --shacl. Use in CI where a silent skip must not pass."
    ),
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit a JSON report instead of the table.",
)
@click.pass_context
def kg_validate(
    ctx: click.Context, db_path: Path, shacl: bool, require_shacl: bool, json_output: bool
) -> None:
    """Check live KG store health: orphan nodes and broken traceability edges.

    Operates on the graph store (not the ``docs/.doc-index.json`` index —
    that is ``context validate``).
    """
    db_path = root_relative_default(ctx, "db_path", db_path, rel=KG_STORE_REL)

    from cataforge.domain.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraph
    from cataforge.domain.kg.validate import validate

    shacl = shacl or require_shacl
    config = KGConfig(store_backend="oxigraph", db_path=db_path)
    try:
        with KnowledgeGraph.connect(config, read_only=True) as kg:
            report = validate(kg.store, config, run_shacl=shacl)
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    if json_output:
        click.echo(
            json.dumps(
                {
                    "ok": report.ok,
                    "shacl_skipped": report.shacl_skipped,
                    "shacl_skip_reason": report.shacl_skip_reason,
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
            click.echo(f"{'Severity':<12} {'Entity':<20} {'Shape':<28} Message")
            click.echo("-" * 80)
            for v in report.violations:
                click.echo(f"{v.severity:<12} {v.entity_id:<20} {v.shape:<28} {v.message}")
        if report.shacl_skipped and shacl:
            click.echo(f"Note: SHACL pass skipped ({report.shacl_skip_reason}).")

    if require_shacl and report.shacl_skipped:
        raise KGVerificationError(
            f"--require-shacl: SHACL pass could not run ({report.shacl_skip_reason}). "
            "Install the `shacl` extra (pyshacl + rdflib) and ensure "
            "_generated/core_shapes.ttl is present."
        )
    if not report.ok:
        raise KGVerificationError("validation reported violations.")


@kg_group.command("export", hidden=True)
@db_path_ro_option()
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("docs"),
    show_default=True,
    help="Root directory for the exported Markdown tree.",
)
@click.option(
    "--per-entity",
    is_flag=True,
    default=False,
    help="Export one Markdown card per entity instead of reconstructing whole documents.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Emit a JSON result blob (per-file sha256 included) instead of the table.",
)
@click.pass_context
def kg_export(
    ctx: click.Context,
    db_path: Path,
    output_dir: Path,
    per_entity: bool,
    json_output: bool,
) -> None:
    """Low-level KG → Markdown export (``--per-entity`` for cards).

    Business flows use ``context finalize``.
    """
    db_path = root_relative_default(ctx, "db_path", db_path, rel=KG_STORE_REL)
    output_dir = root_relative_default(ctx, "output_dir", output_dir, rel=Path("docs"))

    from cataforge.domain.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraph
    from cataforge.domain.kg.export import compile_to_markdown
    from cataforge.domain.kg.export.document_pipeline import compile_documents

    config = KGConfig(store_backend="oxigraph", db_path=db_path)
    try:
        with KnowledgeGraph.connect(config) as kg:
            if per_entity:
                result = compile_to_markdown(kg.store, output_dir)
            else:
                result = compile_documents(kg.store, output_dir)
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    unit = "entities" if per_entity else "documents"
    if json_output:
        click.echo(
            json.dumps(
                {
                    "discovered_count": result.discovered_count,
                    "rendered": len(result.file_records),
                    "errors": [{"entity_id": e, "message": m} for e, m in result.errors],
                    "files": result.file_hashes,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        click.echo(
            f"OK: rendered {len(result.file_records)}/{result.discovered_count} {unit} "
            f"→ {result.output_dir}"
        )
        if result.errors:
            click.echo(f"  errors: {len(result.errors)}")
            for eid, msg in result.errors:
                click.echo(f"   - {eid}: {msg}")

    if result.errors:
        raise KGVerificationError(f"{len(result.errors)} export errors")


@kg_group.command("drift-check")
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing docs/ and .cataforge/.",
)
@db_path_ro_option()
@click.option(
    "--doc-type",
    "doc_types",
    multiple=True,
    help=(
        "Restrict to specific doc_types. Repeatable. Default = the project's "
        "kg_active_doc_types (framework.json context.kg_active_doc_types, "
        "fall-back: the built-in business doc_type set)."
    ),
)
@click.option(
    "--report-output",
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help=(
        "Path to write the JSON report. Default = <project-root>/docs/.kg-reconcile-report.json."
    ),
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Also emit the report to stdout as JSON.",
)
@click.pass_context
def kg_drift_check(
    ctx: click.Context,
    project_root: Path,
    db_path: Path,
    doc_types: tuple[str, ...],
    report_output: Path | None,
    json_output: bool,
) -> None:
    """Low-level symmetric-diff diagnostic between Markdown and the KG store.

    For each active doc_type, compares FS-extracted entities and traceability
    triples against the KG. Writes the diff to `docs/.kg-reconcile-report.json`
    and exits non-zero if any `missing` or `ghost` entry exists. This is a
    store-mechanics diagnostic; the business drift gate is `context reconcile`,
    which decides pass/fail by document-level triage.
    """
    from cataforge.domain.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraph
    from cataforge.domain.kg._dispatch import kg_config_for, kg_enabled
    from cataforge.domain.kg.reconcile import reconcile, write_report

    project_root = root_relative_default(ctx, "project_root", project_root)
    db_path = root_relative_default(ctx, "db_path", db_path, rel=KG_STORE_REL)
    project_root = project_root.resolve()

    if not doc_types and not kg_enabled(project_root):
        click.echo("markdown mode (context.mode): KG disabled — nothing to reconcile.")
        return

    base_config = kg_config_for(project_root)

    active = set(doc_types) if doc_types else set(base_config.kg_active_doc_types)

    if not active:
        click.echo(
            "  (no active doc_types — nothing to reconcile; "
            "set context.kg_active_doc_types in framework.json)"
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
        with KnowledgeGraph.connect(config, read_only=True) as kg:
            report = reconcile(kg.store, project_root, config)
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    output_path = (
        report_output
        if report_output is not None
        else project_root / "docs" / ".kg-reconcile-report.json"
    )
    write_report(report, output_path)

    if json_output:
        click.echo(json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    else:
        click.echo(
            f"reconcile: divergence={report.overall_divergence_count} doc_types={sorted(active)}"
        )
        for dt, per in sorted(report.per_doc_type.items()):
            marker = "OK" if per.divergence_count == 0 else "DRIFT"
            click.echo(
                f"  [{marker}] {dt}: "
                f"missing_entities={len(per.missing_entities)} "
                f"ghost_entities={len(per.ghost_entities)} "
                f"missing_relations={len(per.missing_relations)} "
                f"ghost_relations={len(per.ghost_relations)} "
                f"orphan_relations={len(per.orphan_relations)}"
            )
            if per.missing_entities:
                preview = per.missing_entities[:5]
                ellipsis = "..." if len(per.missing_entities) > 5 else ""
                click.echo(f"        missing_entities: {preview}{ellipsis}")
            if per.ghost_entities:
                preview = per.ghost_entities[:5]
                ellipsis = "..." if len(per.ghost_entities) > 5 else ""
                click.echo(f"        ghost_entities: {preview}{ellipsis}")
            if per.orphan_relations:
                orphan_preview = per.orphan_relations[:5]
                ellipsis = "..." if len(per.orphan_relations) > 5 else ""
                click.echo(f"        orphan_relations (target missing): {orphan_preview}{ellipsis}")
        click.echo(f"  report: {output_path}")

    if not report.ok:
        raise KGVerificationError(
            f"reconcile reported {report.overall_divergence_count} divergence(s); see {output_path}"
        )


@kg_group.command("compare-read")
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing docs/ and .cataforge/.",
)
@db_path_ro_option()
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
@click.pass_context
def kg_compare_read(
    ctx: click.Context,
    project_root: Path,
    db_path: Path,
    doc_types: tuple[str, ...],
    sample_size: int,
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
    from cataforge.domain.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraph
    from cataforge.domain.kg._dispatch import kg_config_for
    from cataforge.domain.kg.compare_read import (
        compare_read,
    )

    project_root = root_relative_default(ctx, "project_root", project_root)
    db_path = root_relative_default(ctx, "db_path", db_path, rel=KG_STORE_REL)
    project_root = project_root.resolve()
    base_config = kg_config_for(project_root)

    active = set(doc_types) if doc_types else set(base_config.kg_active_doc_types)

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
        with KnowledgeGraph.connect(config, read_only=True) as kg:
            report = compare_read(
                kg,
                project_root,
                doc_types=active,
                sample_size=sample_size,
                seed=seed,
            )
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc

    if json_output:
        click.echo(json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
        return

    click.echo(f"compare-read: sampled={report.sampled_count} alarms={len(report.alarms)}")
    if not report.alarms:
        click.echo("  OK (every sampled entity's content_hash matches KG)")
        return
    for alarm in report.alarms[:10]:
        click.echo(f"  ALARM {alarm.entity_id} ({alarm.doc_type}): {alarm.reason}")
    if len(report.alarms) > 10:
        click.echo(f"  ... +{len(report.alarms) - 10} more")
