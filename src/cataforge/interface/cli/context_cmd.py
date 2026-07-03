"""``cataforge context`` — the unified context-IO facade.

One command family over the capability ports: read/relation and the
authoring lifecycle (write → write-narrative → finalize → ingest →
reconcile), all routed by ``context.mode``. This is the
backend-routing door the single ``context`` skill targets; callers never
name the graph or the file store.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import click

from cataforge.core.errors import CataforgeError, KGStoreError
from cataforge.interface.cli._hints import NO_RELATIONS_HINT
from cataforge.interface.cli.main import cli

if TYPE_CHECKING:
    from collections.abc import Generator


@cli.group("context")
def context_group() -> None:
    """Mode-routed context I/O — the single document/context entry point.

    Read & index: ``read`` (section load), ``index`` (build .doc-index.json),
    ``validate`` (read-only index integrity gate). Authoring lifecycle:
    ``write`` / ``write-narrative`` / ``transact`` / ``finalize`` / ``ingest``
    / ``reconcile``. The ``docs`` group's ``load`` / ``index`` / ``validate``
    are deprecated aliases of ``read`` / ``index`` / ``validate``.
    """


@contextmanager
def _kg_store_guard() -> Generator[None]:
    """Turn a missing-store crash into a clean ``Error:`` with an init hint.

    Under ``graph`` the lifecycle commands open the graph; on a
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


def _relations(pairs: tuple[str, ...]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for raw in pairs:
        if "=" not in raw:
            raise click.ClickException(f"--relation expects PREDICATE=OBJECT_ID, got: {raw}")
        predicate, object_id = raw.split("=", 1)
        out.append((predicate.strip(), object_id.strip()))
    return out


def _rooted(ctx: click.Context, project_root: str | None) -> str:
    """Resolve ``--project-root`` to a concrete path, honouring ``--project-dir``.

    Every context command carries its own ``--project-root`` (default ``None``);
    an explicitly-passed value wins, a defaulted one re-roots under the global
    ``--project-dir``, and absent both it falls back to the discovered project
    root. The single return type lets callers drop per-command fallbacks.
    """
    from cataforge.interface.cli.helpers import resolve_root, root_relative_default

    resolved = root_relative_default(ctx, "project_root", project_root)
    return str(resolved) if resolved is not None else str(resolve_root())


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
    """Mode-routed section read of ``doc_id#§N[.item]`` REFS."""
    from cataforge.interface.cli.doc_io import run_load

    run_load(
        refs,
        _rooted(ctx, project_root),
        json_output,
        with_deps,
        budget,
        command_label="context read",
    )


@context_group.command("index")
@click.option("--project-root", default=None)
@click.option(
    "--doc-file",
    default=None,
    help="Incremental update for a single file (otherwise rebuild the full index).",
)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Exit non-zero (3) if any docs/**/*.md is skipped for missing YAML "
    "front matter — useful as a CI gate.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Read-only integrity gate: validate the existing index without "
    "rebuilding or writing. Equivalent to `context validate`.",
)
@click.pass_context
def context_index(
    ctx: click.Context,
    project_root: str | None,
    doc_file: str | None,
    strict: bool,
    dry_run: bool,
) -> None:
    """Build or update the chapter-level JSON index ``docs/.doc-index.json``."""
    from cataforge.interface.cli.doc_io import run_index

    run_index(
        _rooted(ctx, project_root),
        doc_file,
        strict,
        dry_run=dry_run,
        command_label="context index",
    )


@context_group.command("validate")
@click.option("--project-root", default=None)
@click.pass_context
def context_validate(ctx: click.Context, project_root: str | None) -> None:
    """Validate ``docs/.doc-index.json`` integrity without writing to disk.

    Equivalent to ``context index --strict`` but read-only — useful as a
    pre-commit / CI gate that fails fast on:

    \b
    - orphan docs (markdown files missing YAML front matter)
    - stale index entries (file_path no longer on disk)
    - cross-reference errors (frontmatter ``deps`` that don't resolve)
    - alias conflicts (duplicate / shadowed alias claims)
    - invalid ids (doc_id / alias containing '.' or other non-slug chars)

    Exits 0 when clean, 3 when any failure is found.
    """
    from cataforge.interface.cli.doc_io import run_validate

    run_validate(_rooted(ctx, project_root))


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


@context_group.command("status")
@click.option("--project-root", default=None)
@click.option("--json", "json_output", is_flag=True, help="Emit a JSON probe instead of text.")
@click.pass_context
def context_status(ctx: click.Context, project_root: str, json_output: bool) -> None:
    """Print a read-only probe of the project's context backend.

    Reports the resolved ``context.mode`` and, when a graph store is already on
    disk, its entity count. Defaults to a human-readable summary; ``--json``
    emits the machine-readable blob. Probing never creates the store: an
    uninitialized project reads ``store_initialized: false`` with a zero count,
    leaving disk untouched.
    """
    import json

    from cataforge.domain.kg._dispatch import context_mode

    project_root = _rooted(ctx, project_root)
    store_dir = Path(project_root) / ".cataforge" / "kg" / "store"
    payload: dict[str, object] = {
        "mode": context_mode(project_root),
        "store_initialized": store_dir.exists(),
        "entity_count": 0,
    }
    if store_dir.exists():
        from cataforge.domain.kg import KnowledgeGraph
        from cataforge.domain.kg._dispatch import kg_config_for

        cfg = kg_config_for(project_root)
        with _kg_store_guard(), KnowledgeGraph.connect(cfg, read_only=True) as kg:
            payload["entity_count"] = len(kg.query.entity_ids())
    if json_output:
        click.echo(json.dumps(payload))
        return
    click.echo(f"mode: {payload['mode']}")
    click.echo(f"store_initialized: {str(payload['store_initialized']).lower()}")
    click.echo(f"entity_count: {payload['entity_count']}")


@context_group.command("update")
@click.argument("entity_id")
@click.option("--title", default=None, help="New title.")
@click.option("--section", "source_section", default=None, help="New source section anchor.")
@click.option("--slot", "slots", multiple=True, metavar="KEY=VALUE", help="Repeatable scalar slot.")
@click.option("--content-hash", default=None, help="New content hash (idempotent if unchanged).")
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
    project_root: str | None,
    json_output: bool,
) -> None:
    """Business authoring door: in-place slot/title merge on an existing entity
    (graph mode only). Membership (part_of / source_doc) is preserved."""
    import json

    from cataforge.application.context.write import update_entity
    from cataforge.domain.kg import KGEntityNotFoundError

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
            )
        except KGEntityNotFoundError as exc:
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
