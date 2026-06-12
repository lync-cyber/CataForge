"""``cataforge context`` — the unified context-IO facade.

One command family over the capability ports: read/relation and the
authoring lifecycle (write → write-narrative → finalize → ingest →
reconcile), all routed by ``context.strategy``. This is the
backend-routing door the single ``context`` skill targets; callers never
name the graph or the file store.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import click

from cataforge.core.errors import CataforgeError, KGStoreError
from cataforge.interface.cli.main import cli

if TYPE_CHECKING:
    from collections.abc import Generator


@cli.group("context")
def context_group() -> None:
    """Strategy-routed context I/O (read / relation / write lifecycle)."""


@contextmanager
def _kg_store_guard() -> Generator[None]:
    """Turn a missing-store crash into a clean ``Error:`` with an init hint.

    Under ``kg-first`` the authoring/lifecycle commands open the graph; on a
    project that never ran ``cataforge kg init`` the connect raises
    ``KGStoreNotInitializedError``, which would otherwise escape as an
    uncaught traceback. The ``cataforge kg`` twin commands already convert it
    to :class:`KGStoreError`; mirror that here.
    """
    from cataforge.domain.kg import KGStoreNotInitializedError

    try:
        yield
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(f"{exc}\nHint: run `cataforge kg init` first.") from exc


def _kv(pairs: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            raise click.ClickException(f"--slot expects KEY=VALUE, got: {raw}")
        key, value = raw.split("=", 1)
        out[key.strip()] = value
    return out


def _rooted(ctx: click.Context, project_root: str | None) -> str | None:
    """Re-root a defaulted ``--project-root`` under the global ``--project-dir``.

    The context commands carry their own ``--project-root`` (defaulting to
    cwd), so without this they ignore the global flag. An explicitly-passed
    ``--project-root`` still wins.
    """
    from cataforge.interface.cli.helpers import root_relative_default

    resolved = root_relative_default(ctx, "project_root", project_root)
    return str(resolved) if resolved is not None else None


@context_group.command("read")
@click.argument("refs", nargs=-1, required=True)
@click.option("--project-root", default=None)
@click.option("--json", "json_output", is_flag=True)
@click.option("--with-deps", is_flag=True)
@click.option("--budget", type=int, default=None)
@click.pass_context
def context_read(
    ctx: click.Context,
    refs: tuple[str, ...],
    project_root: str | None,
    json_output: bool,
    with_deps: bool,
    budget: int | None,
) -> None:
    """Strategy-routed section read of ``doc_id#§N[.item]`` REFS."""
    from cataforge.application.context.read import main as read_main

    project_root = _rooted(ctx, project_root)
    argv = list(refs)
    if project_root:
        argv += ["--project-root", project_root]
    if json_output:
        argv.append("--json")
    if with_deps:
        argv.append("--with-deps")
    if budget is not None:
        argv += ["--budget", str(budget)]
    raise SystemExit(read_main(argv))


@context_group.command("write")
@click.option("--entity-id", required=True)
@click.option("--class", "class_name", required=True, help="Ontology class, e.g. Feature.")
@click.option("--title", required=True)
@click.option("--slot", "slots", multiple=True, metavar="KEY=VALUE", help="Repeatable scalar slot.")
@click.option("--section", "source_section", default="", help="Source section anchor.")
@click.option("--project-id", default=None)
@click.option("--project-root", default=".")
@click.pass_context
def context_write(
    ctx: click.Context,
    entity_id: str,
    class_name: str,
    title: str,
    slots: tuple[str, ...],
    source_section: str,
    project_id: str | None,
    project_root: str,
) -> None:
    """Authorized write of a single entity into the graph (kg-first strategy only)."""
    from cataforge.application.context.write import author_entity

    project_root = _rooted(ctx, project_root) or project_root
    with _kg_store_guard():
        iri = author_entity(
            project_root,
            entity_id=entity_id,
            class_name=class_name,
            title=title,
            slots=_kv(slots),
            source_section=source_section,
            project_id=project_id,
        )
    click.echo(f"authored {entity_id} -> {iri}")


@context_group.command("write-narrative")
@click.option("--doc-id", required=True)
@click.option("--anchor", required=True, help="Section anchor, e.g. '§1 概览'.")
@click.option("--narrative", default=None, help="Prose body; omit to read from stdin.")
@click.option("--project-root", default=".")
@click.pass_context
def context_write_narrative(
    ctx: click.Context, doc_id: str, anchor: str, narrative: str | None, project_root: str
) -> None:
    """Author a Section's prose into the graph (kg-first strategy only)."""
    from cataforge.application.context.write import write_narrative

    project_root = _rooted(ctx, project_root) or project_root
    body = narrative if narrative is not None else click.get_text_stream("stdin").read()
    with _kg_store_guard():
        write_narrative(project_root, doc_id=doc_id, anchor=anchor, narrative=body)
    click.echo(f"wrote narrative for {doc_id}#{anchor}")


@context_group.command("finalize")
@click.option("--project-root", default=".")
@click.option("--output-dir", default=None, help="Export target (default docs/).")
@click.pass_context
def context_finalize(ctx: click.Context, project_root: str, output_dir: str | None) -> None:
    """Persist authored content (graph export under kg-first, docs-index rebuild under doc-only)."""
    from cataforge.application.context.write import DocIndexResult, finalize

    project_root = _rooted(ctx, project_root) or project_root
    with _kg_store_guard():
        result = finalize(project_root, output_dir)
    if isinstance(result, DocIndexResult):
        click.echo(f"indexed {result.indexed_count} doc(s)")
        return
    click.echo(f"exported {len(result.file_records)} file(s)")
    if result.errors:
        for err in result.errors:
            click.echo(f"[ERROR] {err}", err=True)
        failure = CataforgeError(f"finalize: {len(result.errors)} export error(s)")
        failure.exit_code = 1
        raise failure


@context_group.command("ingest")
@click.option("--project-root", default=".")
@click.option("--doc-type", "doc_types", multiple=True, help="Restrict scope; repeatable.")
@click.pass_context
def context_ingest(ctx: click.Context, project_root: str, doc_types: tuple[str, ...]) -> None:
    """Reflect human-edited Markdown into the active backend (graph or docs index)."""
    from cataforge.application.context.write import DocIndexResult, ingest

    project_root = _rooted(ctx, project_root) or project_root
    with _kg_store_guard():
        stats = ingest(project_root, list(doc_types) or None)
    if isinstance(stats, DocIndexResult):
        click.echo(f"indexed {stats.indexed_count} doc(s)")
        return
    click.echo(
        f"ingested: {stats.write_stats.entities_written} entities, "
        f"{stats.structure_stats.sections_written} sections written"
    )


@context_group.command("reconcile")
@click.option("--project-root", default=".")
@click.pass_context
def context_reconcile(ctx: click.Context, project_root: str) -> None:
    """Drift guard between the Markdown tree and the active backend."""
    from cataforge.application.context.write import reconcile_check

    project_root = _rooted(ctx, project_root) or project_root
    with _kg_store_guard():
        report = reconcile_check(project_root)
    if report.ok:
        click.echo("reconcile OK (no drift)")
        return
    click.echo(f"DRIFT: {report.overall_divergence_count} divergence(s)", err=True)
    failure = CataforgeError(f"reconcile: {report.overall_divergence_count} divergence(s)")
    failure.exit_code = 3
    raise failure
