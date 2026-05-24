"""``cataforge kg`` mutation commands — store init + entity/relation CRUD + adapters.

All commands decorate the ``kg_group`` / ``kg_adapter_group`` defined in
``cataforge.cli.kg_cmd``. Importing this module is a side-effect:
decorators run at import time and register on the group.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from cataforge.cli.kg._common import (
    coerce_set_value,
    load_store,
    project_root_option,
)
from cataforge.cli.kg_cmd import kg_adapter_group, kg_group
from cataforge.core.paths import find_project_root

# ---- storage init -------------------------------------------------------


@kg_group.command("init")
@project_root_option
def kg_init(project_root: Path | None) -> None:
    """Initialise an empty ``.doc-graph/`` store in the project."""
    from cataforge.kg.store import RDFLibStore

    root = project_root or find_project_root()
    store = RDFLibStore()
    store.load(root)
    store.persist()
    click.echo(f"initialised empty graph at {root / 'docs' / '.doc-graph'}")


# ---- entity CRUD --------------------------------------------------------


@kg_group.command("add-entity")
@project_root_option
@click.option("--type", "rdf_type", required=True, help="rdf:type CURIE, e.g. cfa:Feature")
@click.option("--id", "entity_id", required=True, help="cfk:hasId display ID, e.g. F-001")
@click.option(
    "--props",
    "props_json",
    default=None,
    help='JSON object {"predicate_curie": "value", ...}',
)
@click.option(
    "--iri",
    default=None,
    help="Full IRI / CURIE for the subject (defaults to cfa:<id>).",
)
def kg_add_entity(
    project_root: Path | None,
    rdf_type: str,
    entity_id: str,
    props_json: str | None,
    iri: str | None,
) -> None:
    """Create a typed entity with cfk:hasId and optional extra props."""
    from cataforge.kg.store import Triple

    subj = iri or f"cfa:{entity_id}"
    triples: list[Triple] = [
        Triple(s=subj, p="rdf:type", o=rdf_type),
        Triple(s=subj, p="cfk:hasId", o=entity_id),
    ]
    if props_json:
        try:
            props = json.loads(props_json)
        except json.JSONDecodeError as exc:
            raise click.ClickException(f"invalid --props JSON: {exc.msg}") from exc
        if not isinstance(props, dict):
            raise click.ClickException("--props must be a JSON object")
        for pred, value in props.items():
            triples.append(Triple(s=subj, p=str(pred), o=value))
    store, _ = load_store(project_root)
    store.add(triples)
    store.persist()
    click.echo(f"added {len(triples)} triples for {subj}")


@kg_group.command("get-entity")
@project_root_option
@click.argument("subject", required=True)
@click.option(
    "--format",
    "out_format",
    type=click.Choice(["table", "jsonld", "turtle"]),
    default="table",
)
def kg_get_entity(
    project_root: Path | None, subject: str, out_format: str,
) -> None:
    """Show every triple where SUBJECT appears in the subject position."""
    from cataforge.cli.kg._common import expand_or_passthrough
    from cataforge.kg.query import q

    rows = q(
        load_store(project_root)[0],
        sparql=(
            f"SELECT ?p ?o WHERE {{ <{expand_or_passthrough(subject)}> ?p ?o }}"
            " ORDER BY ?p ?o"
        ),
    )
    if out_format == "table":
        for r in rows:
            click.echo(f"{r['p']}\t{r['o']}")
    else:
        from cataforge.kg.store import RDFLibStore
        store: RDFLibStore = load_store(project_root)[0]
        graph = store._dataset.default_graph  # noqa: SLF001
        out = graph.serialize(format=out_format)
        click.echo(out)


@kg_group.command("update-entity")
@project_root_option
@click.argument("subject", required=True)
@click.option(
    "--set",
    "set_assignments",
    multiple=True,
    help='predicate=value (repeatable); value JSON-decoded if it parses as JSON.',
)
def kg_update_entity(
    project_root: Path | None,
    subject: str,
    set_assignments: tuple[str, ...],
) -> None:
    """Set or replace one or more predicate values on SUBJECT.

    Each ``--set pred=value`` first removes any existing (subject, pred, *)
    triples, then inserts (subject, pred, value).
    """
    from cataforge.kg.store import Triple

    if not set_assignments:
        raise click.ClickException("at least one --set required")
    store, _ = load_store(project_root)
    for assignment in set_assignments:
        if "=" not in assignment:
            raise click.ClickException(
                f"--set requires pred=value, got {assignment!r}",
            )
        pred, _, raw = assignment.partition("=")
        value = coerce_set_value(raw.strip())
        store.remove(Triple(s=subject, p=pred.strip(), o="*"))
        store.add([Triple(s=subject, p=pred.strip(), o=value)])
    store.persist()
    click.echo(f"updated {subject} ({len(set_assignments)} predicates)")


@kg_group.command("delete-entity")
@project_root_option
@click.argument("subject", required=True)
def kg_delete_entity(project_root: Path | None, subject: str) -> None:
    """Remove every triple where SUBJECT appears as subject."""
    from cataforge.kg.store import Triple

    store, _ = load_store(project_root)
    removed = store.remove(Triple(s=subject, p="*", o="*"))
    store.persist()
    click.echo(f"removed {removed} triples for {subject}")


# ---- relation CRUD ------------------------------------------------------


@kg_group.command("add-relation")
@project_root_option
@click.argument("src", required=True)
@click.argument("predicate", required=True)
@click.argument("dst", required=True)
def kg_add_relation(
    project_root: Path | None, src: str, predicate: str, dst: str,
) -> None:
    """Add a single (src, predicate, dst) triple."""
    from cataforge.kg.store import Triple

    store, _ = load_store(project_root)
    store.add([Triple(s=src, p=predicate, o=dst)])
    store.persist()
    click.echo(f"+ {src} {predicate} {dst}")


@kg_group.command("remove-relation")
@project_root_option
@click.argument("src", required=True)
@click.argument("predicate", required=True)
@click.argument("dst", required=True)
def kg_remove_relation(
    project_root: Path | None, src: str, predicate: str, dst: str,
) -> None:
    """Remove a single (src, predicate, dst) triple."""
    from cataforge.kg.store import Triple

    store, _ = load_store(project_root)
    removed = store.remove(Triple(s=src, p=predicate, o=dst))
    store.persist()
    click.echo(f"- {src} {predicate} {dst} (removed {removed})")


# ---- adapter dispatch ---------------------------------------------------


@kg_adapter_group.command("list")
def kg_adapter_list() -> None:
    """List every registered adapter (built-ins + plugin-registered)."""
    from cataforge.kg import adapters

    for name in adapters.names():
        cls = adapters.get(name)
        doc = (cls.__doc__ or "").strip().split("\n", 1)[0]
        click.echo(f"  {name:<22} {doc}")


@kg_adapter_group.command("show")
@click.argument("name")
def kg_adapter_show(name: str) -> None:
    """Show an adapter's config_schema as JSON."""
    from cataforge.kg import adapters
    from cataforge.kg.adapters import AdapterError

    try:
        cls = adapters.get(name)
    except AdapterError as exc:
        raise click.ClickException(str(exc)) from exc
    payload = {
        "name": cls.name,
        "class": f"{cls.__module__}.{cls.__name__}",
        "doc": (cls.__doc__ or "").strip(),
        "config_schema": cls.config_schema,
    }
    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@kg_adapter_group.command("context")
@project_root_option
@click.argument("adapter_name")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to the adapter config JSON (the kg_adapter.config block).",
)
@click.option(
    "--params",
    "params_json",
    default="{}",
    help='JSON object of pre_dispatch_context params: {"doc_id": "prd-acme"}',
)
@click.option(
    "--invocation-id",
    "invocation_id",
    default="manual-cli",
    help="Invocation id used for the named-graph IRI on any future write-back.",
)
def kg_adapter_context(
    project_root: Path | None,
    adapter_name: str,
    config_path: Path,
    params_json: str,
    invocation_id: str,
) -> None:
    """Run pre_dispatch_context and emit the result as JSON.

    Mirrors what the harness will inject into the LLM prompt — useful
    for debugging frontmatter SPARQL or verifying that a skill's
    pre-dispatch context reaches the agent in the shape you expect.
    """
    from cataforge.kg import adapters
    from cataforge.kg.adapters import AdapterError

    try:
        cls = adapters.get(adapter_name)
    except AdapterError as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        params = json.loads(params_json)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"invalid JSON: {exc.msg}") from exc

    store, root = load_store(project_root)
    config.setdefault("_project_root", str(root))
    adapter = cls(store=store, invocation_id=invocation_id, config=config)
    try:
        ctx = adapter.pre_dispatch_context(params)
    except AdapterError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(ctx, indent=2, ensure_ascii=False))


@kg_group.command("adapter-migrate")
@project_root_option
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Show what would change without writing.",
)
@click.option(
    "--force",
    "force",
    is_flag=True,
    default=False,
    help="Overwrite existing kg_adapter blocks (default skips user-customised).",
)
def kg_adapter_migrate(
    project_root: Path | None,
    dry_run: bool,
    force: bool,
) -> None:
    """Batch-inject ``kg_adapter`` frontmatter blocks (design §3.5).

    Idempotent: re-running with the same plan leaves files unchanged once
    the canonical block is in place. Schemas are never overwritten — the
    migration owns the frontmatter contract, not the schemas themselves.
    """
    from cataforge.kg.adapter_migrate import (
        AdapterMigrationError,
        migrate_adapters,
    )

    root = project_root or find_project_root()
    try:
        report = migrate_adapters(root, dry_run=dry_run, force=force)
    except AdapterMigrationError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(report.format())
    if report.targets_missing:
        click.echo("")
        click.echo("(missing targets are ok in skeleton projects;"
                   " run `cataforge setup --force-scaffold` first if unexpected.)")


@kg_adapter_group.command("write-back")
@project_root_option
@click.argument("adapter_name")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to the agent output JSON to write back.",
)
@click.option(
    "--invocation-id",
    "invocation_id",
    required=True,
    help="Invocation id used for the named-graph IRI.",
)
@click.option(
    "--validate/--no-validate",
    "do_validate",
    default=False,
    help="Run SHACL validation after write-back (off by default).",
)
def kg_adapter_writeback(
    project_root: Path | None,
    adapter_name: str,
    config_path: Path,
    output_path: Path,
    invocation_id: str,
    do_validate: bool,
) -> None:
    """Apply an agent's output JSON to the KG via the named adapter."""
    from cataforge.kg import adapters
    from cataforge.kg.adapters import AdapterError

    try:
        cls = adapters.get(adapter_name)
    except AdapterError as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        output = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"invalid JSON: {exc.msg}") from exc

    store, root = load_store(project_root)
    config.setdefault("_project_root", str(root))
    adapter = cls(store=store, invocation_id=invocation_id, config=config)
    try:
        triples = adapter.write_back(output)
    except AdapterError as exc:
        raise click.ClickException(str(exc)) from exc
    store.persist()
    click.echo(f"wrote back {len(triples)} triples in graph cfk:invocation/{invocation_id}")
    if do_validate:
        report = adapter.validate_output(triples)
        if report is not None:
            click.echo(f"conforms: {report.conforms}")
            click.echo(f"violations: {report.violation_count}")
            if not report.conforms:
                raise click.exceptions.Exit(1)
