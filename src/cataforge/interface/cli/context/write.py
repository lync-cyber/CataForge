"""cataforge context authoring door — write, write-narrative, write-doc,
write-meta, transact, update, delete."""

from __future__ import annotations

import click

from cataforge.core.errors import CataforgeError, KGStoreError
from cataforge.interface.cli._support._hints import NO_RELATIONS_HINT
from cataforge.interface.cli.context import context_group
from cataforge.interface.cli.context._shared import _kg_store_guard, _kv, _relations, _rooted


@context_group.command("write")
@click.option("--entity-id", required=True)
@click.option("--class", "class_name", required=True, help="Ontology class, e.g. Feature.")
@click.option("--title", required=True)
@click.option("--slot", "slots", multiple=True, metavar="KEY=VALUE", help="Repeatable scalar slot.")
@click.option("--parent", "parent_id", default=None, help="Owning entity id for a subordinate.")
@click.option(
    "--relation",
    "relations",
    multiple=True,
    metavar="PREDICATE=OBJECT_ID",
    help="Repeatable outgoing edge.",
)
@click.option("--narrative", default=None, help="Inline prose body for cf:narrative_body.")
@click.option(
    "--narrative-stdin",
    is_flag=True,
    default=False,
    help="Read the prose body from stdin (multi-line). Mutually exclusive with --narrative.",
)
@click.option("--section", "source_section", default="", help="Source section anchor.")
@click.option("--project-id", default=None)
@click.option("--project-root", default=None)
@click.pass_context
def context_write(
    ctx: click.Context,
    entity_id: str,
    class_name: str,
    title: str,
    slots: tuple[str, ...],
    parent_id: str | None,
    relations: tuple[str, ...],
    narrative: str | None,
    narrative_stdin: bool,
    source_section: str,
    project_id: str | None,
    project_root: str,
) -> None:
    """Business authoring door: mode-routed, write-time-validated single
    entity write into the graph (graph mode only).

    Supports layered authoring: ``--parent`` scopes a subordinate under its
    owner (part_of edge), ``--relation`` adds outgoing traceability edges, and
    a narrative body comes from ``--narrative`` or ``--narrative-stdin``.
    """
    from cataforge.application.context.write import author_entity

    if narrative_stdin and narrative is not None:
        raise click.ClickException("--narrative and --narrative-stdin are mutually exclusive.")
    body = click.get_text_stream("stdin").read() if narrative_stdin else narrative

    project_root = _rooted(ctx, project_root)
    with _kg_store_guard():
        iri = author_entity(
            project_root,
            entity_id=entity_id,
            class_name=class_name,
            title=title,
            slots=_kv(slots),
            source_section=source_section,
            project_id=project_id,
            parent_id=parent_id,
            relations=_relations(relations),
            narrative=body,
        )
    click.echo(f"authored {entity_id} -> {iri}")


@context_group.command("write-narrative")
@click.option("--doc-id", required=True)
@click.option("--anchor", required=True, help="Section anchor (the heading text, e.g. '1. 概览').")
@click.option("--narrative", default=None, help="Prose body; omit to read from stdin.")
@click.option("--project-root", default=None)
@click.pass_context
def context_write_narrative(
    ctx: click.Context, doc_id: str, anchor: str, narrative: str | None, project_root: str
) -> None:
    """Author a Section's prose into the graph (graph mode only)."""
    from cataforge.application.context.write import write_narrative

    project_root = _rooted(ctx, project_root)
    body = narrative if narrative is not None else click.get_text_stream("stdin").read()
    with _kg_store_guard():
        write_narrative(project_root, doc_id=doc_id, anchor=anchor, narrative=body)
    click.echo(f"wrote narrative for {doc_id}#{anchor}")


@context_group.command("write-doc")
@click.option("--file", "doc_file", default=None, help="Markdown path; omit to read stdin.")
@click.option(
    "--source-path",
    default=None,
    help="Override the derived docs/{subdir}/{id}.md source path.",
)
@click.option("--project-root", default=None)
@click.pass_context
def context_write_doc(
    ctx: click.Context, doc_file: str | None, source_path: str | None, project_root: str
) -> None:
    """Author a whole document (structure + entities + relations) into the graph.

    Reads Markdown with frontmatter (``doc_type`` + ``id`` required) from
    --file or stdin and stages the Document node, its Sections (in document
    order), entities, and traceability edges in one transaction (graph mode only).
    """
    from pathlib import Path

    from cataforge.application.context.write import author_document

    markdown_text = (
        Path(doc_file).read_text() if doc_file else click.get_text_stream("stdin").read()
    )
    project_root = _rooted(ctx, project_root)
    with _kg_store_guard():
        result = author_document(project_root, markdown_text, source_path=source_path)
    click.echo(
        f"authored {result.doc_id}: {result.sections_written} sections, "
        f"{result.entities_written} entities, {result.relations_written} relations"
    )
    if result.relations_written == 0 and result.entities_written > 0:
        click.echo(f"  ({NO_RELATIONS_HINT})", err=True)


@context_group.command("write-meta")
@click.argument("doc_id")
@click.option("--status", default=None, help="Document status: draft / review / approved.")
@click.option("--version", default=None, help="Document version string.")
@click.option("--project-root", default=None)
@click.pass_context
def context_write_meta(
    ctx: click.Context,
    doc_id: str,
    status: str | None,
    version: str | None,
    project_root: str,
) -> None:
    """Patch a Document's frontmatter status / version in the graph (graph mode only)."""
    from cataforge.application.context.write import update_document_meta

    if status is None and version is None:
        raise click.ClickException("write-meta requires at least one of --status / --version.")
    project_root = _rooted(ctx, project_root)
    with _kg_store_guard():
        update_document_meta(project_root, doc_id, status=status, version=version)
    fields = ", ".join(
        f"{k}={v}" for k, v in (("status", status), ("version", version)) if v is not None
    )
    click.echo(f"updated meta for {doc_id}: {fields}")


@context_group.command("transact")
@click.option("--file", "spec_file", default=None, help="JSON spec path; omit to read stdin.")
@click.option("--project-root", default=None)
@click.pass_context
def context_transact(ctx: click.Context, spec_file: str | None, project_root: str) -> None:
    """Apply a batch of authoring ops in one atomic transaction (graph mode only).

    Reads a JSON spec ``{"operations": [op, ...]}`` from --file or stdin. Each
    op carries an ``op`` discriminator: ``add_entity`` (entity_id / class /
    title; optional parent / slots / narrative / relations), ``add_relation``
    (subject / predicate / object), or ``write_narrative`` (doc_id / anchor /
    narrative). All ops commit together; any validation violation rolls the
    whole batch back to zero graph residue.
    """
    import json
    from pathlib import Path

    from cataforge.application.context.write import transact

    raw = Path(spec_file).read_text() if spec_file else (click.get_text_stream("stdin").read())
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as exc:
        failure = CataforgeError(f"transact: invalid JSON spec — {exc}")
        failure.exit_code = 2
        raise failure from exc

    project_root = _rooted(ctx, project_root)
    with _kg_store_guard():
        result = transact(project_root, spec)
    click.echo(
        f"transacted {result.entities_written} entities, "
        f"{result.relations_written} relations, {result.sections_written} sections"
    )


@context_group.command("update")
@click.argument("entity_id")
@click.option("--title", default=None, help="New title.")
@click.option("--section", "source_section", default=None, help="New source section anchor.")
@click.option("--slot", "slots", multiple=True, metavar="KEY=VALUE", help="Repeatable scalar slot.")
@click.option("--content-hash", default=None, help="New content hash (idempotent if unchanged).")
@click.option(
    "--ack-status-jump",
    is_flag=True,
    default=False,
    help=(
        "Deliberately allow a task_status move outside the legal lifecycle "
        "(rework of a done/cancelled task, manual repair)."
    ),
)
@click.option("--project-root", default=None)
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def context_update(
    ctx: click.Context,
    entity_id: str,
    title: str | None,
    source_section: str | None,
    slots: tuple[str, ...],
    content_hash: str | None,
    ack_status_jump: bool,
    project_root: str | None,
    json_output: bool,
) -> None:
    """Business authoring door: in-place slot/title merge on an existing entity
    (graph mode only). Membership (part_of / source_doc) is preserved."""
    import json

    from cataforge.application.context.write import update_entity
    from cataforge.domain.kg import KGEntityNotFoundError, KGValidationError

    if not slots and title is None and source_section is None and content_hash is None:
        raise click.ClickException(
            "update requires at least one of: --title, --section, --slot, --content-hash."
        )
    project_root = _rooted(ctx, project_root)
    with _kg_store_guard():
        try:
            result = update_entity(
                project_root,
                entity_id,
                title=title,
                source_section=source_section,
                slots=_kv(slots),
                content_hash=content_hash,
                ack_status_jump=ack_status_jump,
            )
        except KGEntityNotFoundError as exc:
            raise KGStoreError(str(exc)) from exc
        except KGValidationError as exc:
            raise KGStoreError(str(exc)) from exc
    if json_output:
        click.echo(
            json.dumps(
                {
                    "entity_id": result.entity_id,
                    "slots_updated": result.slots_updated,
                    "changed": result.changed,
                }
            )
        )
        return
    verb = "updated" if result.changed else "unchanged"
    click.echo(f"{verb} {result.entity_id} ({', '.join(result.slots_updated) or 'no slots'})")


@context_group.command("delete")
@click.argument("entity_id")
@click.option(
    "--cascade",
    is_flag=True,
    default=False,
    help="Also remove incoming edges; without it, refuses if any exist.",
)
@click.option("--yes", is_flag=True, default=False, help="Skip the confirmation prompt.")
@click.option("--project-root", default=None)
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def context_delete(
    ctx: click.Context,
    entity_id: str,
    cascade: bool,
    yes: bool,
    project_root: str | None,
    json_output: bool,
) -> None:
    """Business authoring door: delete an entity (and optionally its incoming
    edges) from the graph (graph mode only)."""
    import json

    from cataforge.application.context.write import delete_entity
    from cataforge.domain.kg import KGEntityNotFoundError, KGValidationError

    if not yes and not json_output:
        suffix = " (and incoming edges)" if cascade else ""
        if not click.confirm(f"Delete {entity_id}{suffix}?", default=False):
            click.echo("Aborted.")
            return
    project_root = _rooted(ctx, project_root)
    with _kg_store_guard():
        try:
            result = delete_entity(project_root, entity_id, cascade=cascade)
        except KGEntityNotFoundError as exc:
            raise KGStoreError(str(exc)) from exc
        except KGValidationError as exc:
            hint = (
                "\nHint: pass --cascade to remove incoming edges too."
                if "incoming edge" in str(exc)
                else ""
            )
            raise KGStoreError(f"{exc}{hint}") from exc
    if json_output:
        click.echo(
            json.dumps(
                {
                    "entity_id": result.entity_id,
                    "cascade": result.cascade,
                    "quads_removed": result.quads_removed,
                }
            )
        )
        return
    tail = ", cascade" if result.cascade else ""
    click.echo(f"deleted {result.entity_id} ({result.quads_removed} quads removed{tail})")
