"""cataforge context backend-sync lifecycle — finalize, ingest, ensure-store,
reconcile."""

from __future__ import annotations

import click

from cataforge.core.errors import CataforgeError
from cataforge.interface.cli.context import context_group
from cataforge.interface.cli.context._shared import _kg_store_guard, _rooted


@context_group.command("finalize")
@click.option("--project-root", default=None)
@click.option("--output-dir", default=None, help="Export target (default docs/).")
@click.option("--doc-type", "doc_types", multiple=True, help="Restrict scope; repeatable.")
@click.option(
    "--dry-run", is_flag=True, help="Preview the per-document export plan without writing."
)
@click.option(
    "--force", is_flag=True, help="Overwrite files whose Markdown is ahead of the export baseline."
)
@click.pass_context
def context_finalize(
    ctx: click.Context,
    project_root: str,
    output_dir: str | None,
    doc_types: tuple[str, ...],
    dry_run: bool,
    force: bool,
) -> None:
    """Persist authored content per mode (graph exports md; else rebuilds the docs index).

    A document whose on-disk Markdown holds changes the graph has not absorbed
    is left untouched and reported; run `cataforge context ingest` first, or
    pass --force to overwrite (the prior file is backed up under
    .cataforge/.backups/).
    """
    from collections import Counter

    from cataforge.application.context.write import DocIndexResult, finalize

    project_root = _rooted(ctx, project_root)
    with _kg_store_guard():
        result = finalize(
            project_root,
            output_dir,
            doc_types=list(doc_types) or None,
            dry_run=dry_run,
            force=force,
        )
    if isinstance(result, DocIndexResult):
        click.echo(f"indexed {result.indexed_count} doc(s)")
        return
    if dry_run:
        for source_path, status in result.plan:
            click.echo(f"{status:9} {source_path}")
        counts = Counter(status for _, status in result.plan)
        summary = " · ".join(f"{counts[s]} {s}" for s in ("new", "update", "unchanged", "blocked"))
        click.echo(f"plan: {summary} (dry-run; nothing written)")
        return
    click.echo(f"exported {len(result.file_records)} file(s)")
    if result.blocked:
        for source_path in result.blocked:
            click.echo(f"[BLOCKED] {source_path}", err=True)
        failure = CataforgeError(
            f"finalize: {len(result.blocked)} file(s) hold Markdown changes the graph has not "
            "absorbed — run `cataforge context ingest` first, or pass --force to overwrite."
        )
        failure.exit_code = 1
        raise failure
    if result.errors:
        for err in result.errors:
            click.echo(f"[ERROR] {err}", err=True)
        failure = CataforgeError(f"finalize: {len(result.errors)} export error(s)")
        failure.exit_code = 1
        raise failure


@context_group.command("ingest")
@click.option("--project-root", default=None)
@click.option("--doc-type", "doc_types", multiple=True, help="Restrict scope; repeatable.")
@click.pass_context
def context_ingest(ctx: click.Context, project_root: str, doc_types: tuple[str, ...]) -> None:
    """Reflect human-edited Markdown into the active backend (graph or docs index)."""
    from cataforge.application.context.write import DocIndexResult, ingest

    project_root = _rooted(ctx, project_root)
    with _kg_store_guard():
        stats = ingest(project_root, list(doc_types) or None)
    if isinstance(stats, DocIndexResult):
        click.echo(f"indexed {stats.indexed_count} doc(s)")
        return
    click.echo(
        f"ingested: {stats.write_stats.entities_written} entities, "
        f"{stats.structure_stats.sections_written} sections written"
    )


@context_group.command("ensure-store")
@click.option("--project-root", default=None)
@click.pass_context
def context_ensure_store(ctx: click.Context, project_root: str) -> None:
    """Rebuild the KG store per context.mode after a clone (it is gitignored).

    graph restores the latest NQuads snapshot; markdown is a no-op.
    Idempotent — a populated store is left as-is.
    """
    from cataforge.application.context.write import ensure_store

    project_root = _rooted(ctx, project_root)
    with _kg_store_guard():
        result = ensure_store(project_root)
    click.echo(f"{result.action}: {result.detail}")


@context_group.command("reconcile")
@click.option("--project-root", default=None)
@click.option("--json", "json_output", is_flag=True, help="Emit the full drift report as JSON.")
@click.pass_context
def context_reconcile(ctx: click.Context, project_root: str, json_output: bool) -> None:
    """Drift guard between the Markdown tree and the active backend.

    The pass/fail verdict is the authoritative document-level three-way triage;
    ``--json`` additionally surfaces the per-doc_type symmetric diff (demoted to
    diagnostics) and every drifted document's state for inspection.
    """
    import json

    from cataforge.application.context.write import DocValidationReport, reconcile_check

    project_root = _rooted(ctx, project_root)
    with _kg_store_guard():
        report = reconcile_check(project_root)
    if json_output:
        if isinstance(report, DocValidationReport):
            payload: dict[str, object] = {
                "ok": report.ok,
                "overall_divergence_count": report.overall_divergence_count,
                "issue_counts": report.issue_counts,
            }
        else:
            payload = report.to_dict()
        click.echo(json.dumps(payload))
        if report.ok:
            return
        failure = CataforgeError(f"reconcile: {report.gate_summary}")
        failure.exit_code = 3
        raise failure
    if report.ok:
        click.echo("reconcile OK (no drift)")
        return
    click.echo(f"DRIFT: {report.gate_summary}", err=True)
    failure = CataforgeError(f"reconcile: {report.gate_summary}")
    failure.exit_code = 3
    raise failure
