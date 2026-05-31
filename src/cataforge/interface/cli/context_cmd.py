"""``cataforge context`` — the unified context-IO facade.

One command family over the capability ports: read/relation (routed by
``context.strategy``) and the KG-first authoring lifecycle
(write → write-narrative → finalize → ingest → reconcile). This is the
backend-routing door the single ``context`` skill targets; callers never
name the graph or the file store.
"""

from __future__ import annotations

import click

from cataforge.interface.cli.main import cli


@cli.group("context")
def context_group() -> None:
    """Strategy-routed context I/O (read / relation / write lifecycle)."""


def _kv(pairs: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            raise click.ClickException(f"--slot expects KEY=VALUE, got: {raw}")
        key, value = raw.split("=", 1)
        out[key.strip()] = value
    return out


@context_group.command("read")
@click.argument("refs", nargs=-1, required=True)
@click.option("--project-root", default=None)
@click.option("--json", "json_output", is_flag=True)
@click.option("--with-deps", is_flag=True)
@click.option("--budget", type=int, default=None)
def context_read(
    refs: tuple[str, ...],
    project_root: str | None,
    json_output: bool,
    with_deps: bool,
    budget: int | None,
) -> None:
    """Strategy-routed section read of ``doc_id#§N[.item]`` REFS."""
    from cataforge.application.context.read import main as read_main

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
def context_write(
    entity_id: str,
    class_name: str,
    title: str,
    slots: tuple[str, ...],
    source_section: str,
    project_id: str | None,
    project_root: str,
) -> None:
    """KG-first authorized write of a single entity (validated at write time)."""
    from cataforge.application.context.write import author_entity

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
def context_write_narrative(
    doc_id: str, anchor: str, narrative: str | None, project_root: str
) -> None:
    """Author a Section's prose (``narrative_body``) into the graph."""
    from cataforge.application.context.write import write_narrative

    body = narrative if narrative is not None else click.get_text_stream("stdin").read()
    write_narrative(project_root, doc_id=doc_id, anchor=anchor, narrative=body)
    click.echo(f"wrote narrative for {doc_id}#{anchor}")


@context_group.command("finalize")
@click.option("--project-root", default=".")
@click.option("--output-dir", default=None, help="Export target (default docs/).")
def context_finalize(project_root: str, output_dir: str | None) -> None:
    """Export the graph to Markdown for human review (KG → md)."""
    from cataforge.application.context.write import finalize

    result = finalize(project_root, output_dir)
    click.echo(f"exported {len(result.file_records)} file(s)")
    if result.errors:
        for err in result.errors:
            click.echo(f"[ERROR] {err}", err=True)
        raise SystemExit(2)


@context_group.command("ingest")
@click.option("--project-root", default=".")
@click.option("--doc-type", "doc_types", multiple=True, help="Restrict scope; repeatable.")
def context_ingest(project_root: str, doc_types: tuple[str, ...]) -> None:
    """Reflect human-edited Markdown back into the graph (md → KG)."""
    from cataforge.application.context.write import ingest

    stats = ingest(project_root, list(doc_types) or None)
    click.echo(
        f"ingested: {stats.write_stats.entities_written} entities, "
        f"{stats.structure_stats.sections_written} sections written"
    )


@context_group.command("reconcile")
@click.option("--project-root", default=".")
def context_reconcile(project_root: str) -> None:
    """Drift guard between the graph and the exported Markdown."""
    from cataforge.application.context.write import reconcile_check

    report = reconcile_check(project_root)
    if report.ok:
        click.echo("reconcile OK (no drift)")
        return
    click.echo(f"DRIFT: {report.overall_divergence_count} divergence(s)", err=True)
    raise SystemExit(3)
