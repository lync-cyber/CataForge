"""cataforge kg — knowledge-graph CLI surface.

Subcommands map 1:1 onto the §2.5 catalogue in
``docs/research/kg-feature-upgrade-design.md``. The Wave A/B/C set
covers storage management (init, migrate, benchmark), entity and
relation CRUD, query, validate, render, ingest, export, coverage, and
template lint. Reasoning (infer / impact / explain), visualisation
(viz), adapter management, and conflict resolution belong to later
waves.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from cataforge.cli.main import cli
from cataforge.core.paths import find_project_root


@cli.group("kg")
def kg_group() -> None:
    """Knowledge-graph store, query, render, validate, and benchmark.

    See ``docs/research/kg-feature-upgrade-design.md`` for the full design.
    """


@kg_group.command("benchmark")
@click.option(
    "--budget",
    "budget_path",
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
    default=None,
    help="Path to perf-budget.json (defaults to <project>/.cataforge/kg/perf-budget.json).",
)
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Project root (defaults to walk-up search for .cataforge/).",
)
def kg_benchmark(budget_path: Path | None, project_root: Path | None) -> None:
    """Run the KG performance-budget gate.

    Per design note §8, budget breaches surface as WARN (not FAIL) so
    cross-machine CI variance doesn't flap. Exit code is always 0 —
    consumers wanting hard enforcement should grep the report for WARN.
    """
    from cataforge.kg.benchmark import (
        format_report,
        load_budget,
        run_benchmarks,
    )

    root = project_root or find_project_root()
    default_budget_path = root / ".cataforge" / "kg" / "perf-budget.json"
    budget_file: Path | None = budget_path or (
        default_budget_path if default_budget_path.is_file() else None
    )
    budget = load_budget(budget_file)

    results = run_benchmarks(root, budget=budget)
    click.echo(format_report(results, budget=budget))


@kg_group.command("migrate")
@click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Project root (defaults to walk-up search for .cataforge/).",
)
@click.option(
    "--rollback",
    is_flag=True,
    default=False,
    help="Restore the most recent .doc-graph.bak.<stamp>/ backup.",
)
@click.option(
    "--no-validate",
    "validate",
    flag_value=False,
    default=True,
    help="Skip the post-migration SHACL validation (validation is warn-only).",
)
def kg_migrate(
    project_root: Path | None,
    rollback: bool,
    validate: bool,
) -> None:
    """Big-bang migrate docs/.doc-index.json into the KG store.

    Existing ``.doc-graph/`` is rotated to a timestamped backup before
    the new graph is written. ``--rollback`` restores the most recent
    backup. SHACL validation is reported but never blocks — fix any
    flagged shapes incrementally after the migration lands.
    """
    from cataforge.kg.migrate import MigrationError, migrate

    root = project_root or find_project_root()
    try:
        report = migrate(root, rollback=rollback, validate=validate)
    except MigrationError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(report.format())


# ===========================================================================
# Storage / lifecycle
# ===========================================================================


_project_root_option = click.option(
    "--project-root",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Project root (defaults to walk-up search for .cataforge/).",
)


def _load_store(project_root: Path | None) -> tuple[Any, Path]:
    from cataforge.kg.store import RDFLibStore
    root = Path(project_root) if project_root is not None else find_project_root()
    store = RDFLibStore()
    store.load(root)
    return store, root


def _store_to_graph(store: Any) -> Any:
    """Materialise a GraphStore's quads into a plain rdflib Graph.

    Reasoning ignores named-graph context (the inference closure is
    over the asserted set, not per-graph). The result is feedable to
    :func:`cataforge.kg.reasoning.infer` directly."""
    from rdflib import Graph

    from cataforge.kg.ontology import bind_namespaces
    from cataforge.kg.store import _object_to_node, _term_to_node

    g = Graph()
    bind_namespaces(g)
    for s, p, o, _ in store:
        g.add((
            _term_to_node(s),
            _term_to_node(p),
            _object_to_node(o),
        ))
    return g


@kg_group.command("init")
@_project_root_option
def kg_init(project_root: Path | None) -> None:
    """Initialise an empty ``.doc-graph/`` store in the project."""
    from cataforge.kg.store import RDFLibStore

    root = project_root or find_project_root()
    store = RDFLibStore()
    store.load(root)
    store.persist()
    click.echo(f"initialised empty graph at {root / 'docs' / '.doc-graph'}")


# ===========================================================================
# Query
# ===========================================================================


@kg_group.command("query")
@_project_root_option
@click.option("--sparql", "sparql", default=None, help="SPARQL query string.")
@click.option(
    "--sparql-file",
    "sparql_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Read SPARQL from a file.",
)
@click.option(
    "--dsl",
    "dsl_json",
    default=None,
    help="JSON DSL: {'rel': ..., 'src_type': ..., 'dst_type': ..., ...}",
)
@click.option(
    "--cypher",
    "cypher",
    default=None,
    help="Single-pattern Cypher: MATCH (a:X)-[:rel]->(b:Y) RETURN a, b",
)
def kg_query(
    project_root: Path | None,
    sparql: str | None,
    sparql_file: Path | None,
    dsl_json: str | None,
    cypher: str | None,
) -> None:
    """Run a query and emit rows as JSON Lines."""
    from cataforge.kg.query import cypher_lite, q

    sources = [s for s in (sparql, sparql_file, dsl_json, cypher) if s is not None]
    if len(sources) != 1:
        raise click.ClickException(
            "pass exactly one of --sparql / --sparql-file / --dsl / --cypher",
        )
    store, _ = _load_store(project_root)
    if sparql_file is not None:
        sparql = sparql_file.read_text(encoding="utf-8")
    if sparql is not None:
        rows = q(store, sparql=sparql)
    elif dsl_json is not None:
        try:
            dsl = json.loads(dsl_json)
        except json.JSONDecodeError as exc:
            raise click.ClickException(f"invalid --dsl JSON: {exc.msg}") from exc
        rows = q(store, dsl=dsl)
    else:
        assert cypher is not None
        rows = cypher_lite(store, cypher)
    for row in rows:
        click.echo(json.dumps(row, ensure_ascii=False))


# ===========================================================================
# Validate
# ===========================================================================


@kg_group.command("validate")
@_project_root_option
@click.option(
    "--shape",
    "shape_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="External SHACL shapes file (defaults to bundled L0/L1/L2 + L3).",
)
def kg_validate(project_root: Path | None, shape_file: Path | None) -> None:
    """Run SHACL validation against the bundled (or external) shape graph.

    Exit code reflects conformance: 0 on conforms, 1 on violation."""
    from cataforge.kg.ontology import load_shapes
    from cataforge.kg.reasoning import validate as reasoning_validate
    from cataforge.kg.store import graph_dir_for

    store, root = _load_store(project_root)
    if shape_file is None:
        gdir = graph_dir_for(root)
        gdir.mkdir(parents=True, exist_ok=True)
        shapes = load_shapes(root, include_l3=True, strict=True)
        tmp_shapes = gdir / "_shapes.tmp.ttl"
        shapes.serialize(destination=str(tmp_shapes), format="turtle")
        try:
            report = reasoning_validate(store, shape_graph=tmp_shapes)
        finally:
            tmp_shapes.unlink(missing_ok=True)
    else:
        report = reasoning_validate(store, shape_graph=shape_file)
    click.echo(f"conforms: {report.conforms}")
    click.echo(f"violations: {report.violation_count}")
    if not report.conforms and report.results_text:
        click.echo("")
        click.echo(report.results_text)
        raise click.exceptions.Exit(1)


# ===========================================================================
# Entity / relation CRUD
# ===========================================================================


@kg_group.command("add-entity")
@_project_root_option
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
    store, _ = _load_store(project_root)
    store.add(triples)
    store.persist()
    click.echo(f"added {len(triples)} triples for {subj}")


@kg_group.command("get-entity")
@_project_root_option
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
    from cataforge.kg.query import q

    rows = q(
        _load_store(project_root)[0],
        sparql=(
            f"SELECT ?p ?o WHERE {{ <{_expand_or_passthrough(subject)}> ?p ?o }}"
            " ORDER BY ?p ?o"
        ),
    )
    if out_format == "table":
        for r in rows:
            click.echo(f"{r['p']}\t{r['o']}")
    else:
        # turtle / jsonld via the store
        from cataforge.kg.store import RDFLibStore
        store: RDFLibStore = _load_store(project_root)[0]
        graph = store._dataset.default_graph  # noqa: SLF001
        out = graph.serialize(format=out_format)
        click.echo(out)


@kg_group.command("update-entity")
@_project_root_option
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
    triples, then inserts (subject, pred, value)."""
    from cataforge.kg.store import Triple

    if not set_assignments:
        raise click.ClickException("at least one --set required")
    store, _ = _load_store(project_root)
    for assignment in set_assignments:
        if "=" not in assignment:
            raise click.ClickException(
                f"--set requires pred=value, got {assignment!r}",
            )
        pred, _, raw = assignment.partition("=")
        value = _coerce_set_value(raw.strip())
        store.remove(Triple(s=subject, p=pred.strip(), o="*"))
        store.add([Triple(s=subject, p=pred.strip(), o=value)])
    store.persist()
    click.echo(f"updated {subject} ({len(set_assignments)} predicates)")


@kg_group.command("delete-entity")
@_project_root_option
@click.argument("subject", required=True)
def kg_delete_entity(project_root: Path | None, subject: str) -> None:
    """Remove every triple where SUBJECT appears as subject."""
    from cataforge.kg.store import Triple

    store, _ = _load_store(project_root)
    removed = store.remove(Triple(s=subject, p="*", o="*"))
    store.persist()
    click.echo(f"removed {removed} triples for {subject}")


@kg_group.command("add-relation")
@_project_root_option
@click.argument("src", required=True)
@click.argument("predicate", required=True)
@click.argument("dst", required=True)
def kg_add_relation(
    project_root: Path | None, src: str, predicate: str, dst: str,
) -> None:
    """Add a single (src, predicate, dst) triple."""
    from cataforge.kg.store import Triple

    store, _ = _load_store(project_root)
    store.add([Triple(s=src, p=predicate, o=dst)])
    store.persist()
    click.echo(f"+ {src} {predicate} {dst}")


@kg_group.command("remove-relation")
@_project_root_option
@click.argument("src", required=True)
@click.argument("predicate", required=True)
@click.argument("dst", required=True)
def kg_remove_relation(
    project_root: Path | None, src: str, predicate: str, dst: str,
) -> None:
    """Remove a single (src, predicate, dst) triple."""
    from cataforge.kg.store import Triple

    store, _ = _load_store(project_root)
    removed = store.remove(Triple(s=src, p=predicate, o=dst))
    store.persist()
    click.echo(f"- {src} {predicate} {dst} (removed {removed})")


# ===========================================================================
# Ingest
# ===========================================================================


@kg_group.command("ingest")
@_project_root_option
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Ingest a single Markdown file. Mutually exclusive with --all.",
)
@click.option(
    "--all",
    "all_flag",
    is_flag=True,
    default=False,
    help="Ingest every docs/**/*.md file (equivalent to `kg migrate`).",
)
@click.option(
    "--auto",
    "auto",
    is_flag=True,
    default=False,
    help=(
        "Quiet-fail mode for the PostToolUse hook (design §4.4 / R-16). "
        "Always exits 0; silently swallows errors so an LLM Edit is "
        "never blocked. Use with --file."
    ),
)
def kg_ingest(
    project_root: Path | None,
    file_path: Path | None,
    all_flag: bool,
    auto: bool,
) -> None:
    """Re-ingest a Markdown file (or all of them) into the graph.

    With ``--file`` the file is parsed and any new/changed triples are
    folded in via the delta engine (kg-wins for conflicts). With ``--all``
    the call delegates to ``kg migrate`` for the big-bang re-ingest.
    ``--auto`` is the PostToolUse entry point — same parsing path, but
    every error is swallowed and exit code is forced to 0."""
    try:
        _do_ingest(project_root, file_path, all_flag)
    except Exception as exc:
        if not auto:
            raise
        click.echo(f"kg ingest --auto: silently skipped ({exc})", err=True)


def _do_ingest(
    project_root: Path | None,
    file_path: Path | None,
    all_flag: bool,
) -> None:
    from cataforge.kg.delta import apply as delta_apply
    from cataforge.kg.delta import compute_delta
    from cataforge.kg.ingest.markdown import ingest_markdown
    from cataforge.kg.migrate import migrate

    if (file_path is None) == (not all_flag):
        raise click.ClickException(
            "pass exactly one of --file or --all",
        )
    root = project_root or find_project_root()
    if all_flag:
        report = migrate(root, validate=False)
        click.echo(report.format())
        return
    assert file_path is not None
    store, _ = _load_store(root)
    result = ingest_markdown(file_path, project_root=root)
    if result.document is None:
        click.echo(f"skipped {file_path}: no frontmatter id")
        return
    scope = {result.document.iri} | {it.iri for it in result.items}
    kg_triples = [
        _shorten_triple(s, p, o) for s, p, o, _ in store
    ]
    delta = compute_delta(
        kg_triples, result.triples, subject_scope=scope,
    )
    added = delta_apply(delta, store, strategy="kg-wins")
    store.persist()
    if delta.conflicts:
        from cataforge.kg.delta import write_conflict_files

        written = write_conflict_files(
            delta,
            project_root=root,
            doc_id=(
                result.document.iri.split("/", 1)[-1] if result.document else None
            ),
        )
        click.echo(
            f"wrote {len(written)} conflict file(s) under docs/.doc-graph/conflicts/",
            err=True,
        )
    click.echo(delta.format())
    click.echo(f"\napplied {added} additions; {len(delta.conflicts)} conflicts kept")


# ===========================================================================
# Conflicts — list / resolve
# ===========================================================================


@kg_group.command("conflicts")
@_project_root_option
def kg_conflicts(project_root: Path | None) -> None:
    """List pending KG conflicts (under docs/.doc-graph/conflicts/)."""
    from cataforge.kg.store import graph_dir_for

    root = project_root or find_project_root()
    cdir = graph_dir_for(root) / "conflicts"
    if not cdir.is_dir():
        click.echo("no conflicts (no conflicts/ directory)")
        return
    pending = sorted(cdir.glob("*.json"))
    if not pending:
        click.echo("no pending conflicts")
        return
    click.echo(f"{len(pending)} pending conflict(s):")
    for p in pending:
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            click.echo(f"  {p.name}: (invalid JSON)")
            continue
        click.echo(
            f"  {payload['conflict_id']} "
            f"[{payload['doc']}] {payload['subject']} {payload['predicate']}",
        )
        click.echo(f"      kg=  {payload['kg_value']['value']!r}")
        click.echo(f"      file={payload['file_value']['value']!r}")


@kg_group.command("resolve")
@_project_root_option
@click.argument("conflict_id")
@click.option(
    "--pick",
    "pick",
    type=click.Choice(["kg", "file", "merge"]),
    required=True,
)
@click.option(
    "--value",
    "merge_value",
    default=None,
    help="Required when --pick merge — the manually-chosen replacement value.",
)
def kg_resolve(
    project_root: Path | None,
    conflict_id: str,
    pick: str,
    merge_value: str | None,
) -> None:
    """Resolve one queued conflict (writes the choice to the store)."""
    from cataforge.kg.store import Triple, graph_dir_for

    root = project_root or find_project_root()
    cdir = graph_dir_for(root) / "conflicts"
    if not cdir.is_dir():
        raise click.ClickException("no conflicts/ directory")
    candidates = [
        p for p in cdir.glob("*.json")
        if conflict_id in p.name
    ]
    if not candidates:
        raise click.ClickException(f"no conflict found matching {conflict_id!r}")
    if len(candidates) > 1:
        raise click.ClickException(
            f"ambiguous conflict id {conflict_id!r}: matches "
            f"{[c.name for c in candidates]}",
        )
    target_path = candidates[0]
    payload = json.loads(target_path.read_text(encoding="utf-8"))

    store, _ = _load_store(root)
    subj = payload["subject"]
    pred = payload["predicate"]
    kg_value = payload["kg_value"]["value"]
    file_value = payload["file_value"]["value"]

    if pick == "kg":
        chosen = kg_value
    elif pick == "file":
        chosen = file_value
    else:
        if merge_value is None:
            raise click.ClickException("--pick merge requires --value")
        chosen = merge_value

    # Remove any existing value (functional predicate — single-valued by
    # ontology contract) then add the chosen one.
    if kg_value is not None:
        store.remove(Triple(s=subj, p=pred, o=kg_value))
    if file_value is not None and file_value != kg_value:
        store.remove(Triple(s=subj, p=pred, o=file_value))
    if chosen is not None:
        store.add([Triple(s=subj, p=pred, o=chosen)])
    store.persist()
    target_path.unlink()
    click.echo(f"resolved {conflict_id}: {subj} {pred} → {chosen!r}")


# ===========================================================================
# Export
# ===========================================================================


@kg_group.command("export")
@_project_root_option
@click.option(
    "--format",
    "out_format",
    type=click.Choice(["turtle", "jsonld", "nquads", "graphml"]),
    default="turtle",
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
)
def kg_export(
    project_root: Path | None, out_format: str, out_path: Path,
) -> None:
    """Export the graph to a single file in the requested format."""
    store, _ = _load_store(project_root)
    if out_format == "graphml":
        out_path.write_text(_to_graphml(store), encoding="utf-8")
    else:
        rdflib_format = {"jsonld": "json-ld", "nquads": "nquads"}.get(
            out_format, out_format,
        )
        data = store._dataset.serialize(format=rdflib_format)  # noqa: SLF001
        out_path.write_text(str(data), encoding="utf-8")
    click.echo(f"wrote {out_path}")


# ===========================================================================
# Render
# ===========================================================================


_DEFAULT_TEMPLATE_DIR = (
    Path(".cataforge") / "skills" / "doc-gen" / "templates" / "standard"
)


def _resolve_template_roots(root: Path) -> list[Path]:
    candidates = [root / _DEFAULT_TEMPLATE_DIR, root / "docs" / "templates"]
    return [p for p in candidates if p.is_dir()]


@kg_group.command("render")
@_project_root_option
@click.option(
    "--doc",
    "doc_iri",
    default=None,
    help="Document CURIE/IRI to render (e.g. cfk:doc/prd-acme).",
)
@click.option(
    "--template",
    "template_name",
    default=None,
    help="Template name relative to the template roots (e.g. prd.md.j2).",
)
@click.option(
    "--project",
    "project_name",
    default=None,
    help="Project slug passed into the template context.",
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output file (default: print to stdout).",
)
@click.option(
    "--check",
    is_flag=True,
    default=False,
    help="Render every PoC template twice and fail on any non-idempotent output.",
)
def kg_render(
    project_root: Path | None,
    doc_iri: str | None,
    template_name: str | None,
    project_name: str | None,
    out_path: Path | None,
    check: bool,
) -> None:
    """Render KG → markdown via Jinja2 templates."""
    from cataforge.kg.render.checker import check_render_idempotent
    from cataforge.kg.render.engine import KGRenderer

    store, root = _load_store(project_root)
    template_roots = _resolve_template_roots(root)
    if not template_roots:
        raise click.ClickException(
            f"no template root found (tried {[str(p) for p in [root / _DEFAULT_TEMPLATE_DIR]]})",
        )
    renderer = KGRenderer(store, template_roots=template_roots)

    if check:
        failures: list[str] = []
        for tpl_root in template_roots:
            for tpl in sorted(tpl_root.glob("*.md.j2")):
                check_ctx: dict[str, Any] = {
                    "doc": "cfk:doc/_check_", "project": "_check_",
                }
                try:
                    result = check_render_idempotent(
                        renderer, tpl.name, **check_ctx,
                    )
                except Exception as exc:
                    click.echo(f"{tpl.name}: render error: {exc}")
                    failures.append(tpl.name)
                    continue
                status = "OK" if result.is_idempotent else "FAIL"
                click.echo(f"{tpl.name}: {status}")
                if not result.is_idempotent:
                    failures.append(tpl.name)
        if failures:
            raise click.exceptions.Exit(1)
        return

    if not (doc_iri and template_name):
        raise click.ClickException(
            "--doc and --template are required unless --check is given",
        )
    ctx: dict[str, Any] = {"doc": doc_iri, "project": project_name or doc_iri}
    out = renderer.render(template_name, **ctx)
    if out_path is None:
        click.echo(out)
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out, encoding="utf-8")
        click.echo(f"wrote {out_path}")


# ===========================================================================
# Coverage
# ===========================================================================


@kg_group.command("coverage")
@_project_root_option
@click.option(
    "--preset",
    "preset",
    type=click.Choice(["rtm", "test", "risk", "interface"]),
    default=None,
)
@click.option("--rows", "rows_class", default=None, help="rows class CURIE")
@click.option("--cols", "cols_class", default=None, help="cols class CURIE")
@click.option("--via", "via_pred", default=None, help="predicate CURIE")
@click.option(
    "--direction",
    type=click.Choice(["col_to_row", "row_to_col"]),
    default="col_to_row",
)
@click.option(
    "--format",
    "out_format",
    type=click.Choice(["table", "json", "markdown", "mermaid"]),
    default="table",
)
def kg_coverage(
    project_root: Path | None,
    preset: str | None,
    rows_class: str | None,
    cols_class: str | None,
    via_pred: str | None,
    direction: str,
    out_format: str,
) -> None:
    """Render a row × col coverage matrix + GAP list."""
    from cataforge.kg.query import coverage

    store, _ = _load_store(project_root)
    if preset is None and not (rows_class and cols_class and via_pred):
        raise click.ClickException(
            "pass --preset or all three of --rows/--cols/--via",
        )
    matrix = coverage(
        store,
        rows_class=rows_class or "",
        cols_class=cols_class or "",
        via=via_pred or "",
        direction=direction,
        preset=preset,
    )
    click.echo(_format_coverage(matrix, out_format))


def _format_coverage(matrix: Any, out_format: str) -> str:
    if out_format == "json":
        return json.dumps({
            "rows": matrix.rows,
            "cols": matrix.cols,
            "cells": [
                {"row": r, "col": c, "covered": True}
                for (r, c) in matrix.cells
            ],
            "gaps": matrix.gaps,
            "coverage_ratio": matrix.coverage_ratio,
        }, ensure_ascii=False, indent=2)
    if out_format == "markdown":
        header = "| row \\ col | " + " | ".join(matrix.cols) + " |"
        sep = "| --- | " + " | ".join("---" for _ in matrix.cols) + " |"
        body = []
        for r in matrix.rows:
            row_cells = [
                "y" if (r, c) in matrix.cells else "-"
                for c in matrix.cols
            ]
            body.append(f"| {r} | " + " | ".join(row_cells) + " |")
        gap_line = (
            f"\n**Gaps**: {', '.join(matrix.gaps)}" if matrix.gaps else ""
        )
        return "\n".join([header, sep, *body]) + gap_line
    if out_format == "mermaid":
        lines = ["graph LR"]
        for r, c in sorted(matrix.cells):
            lines.append(
                f"  {_safe(r)} --> {_safe(c)}",
            )
        return "\n".join(lines)
    # table (default)
    lines = []
    for r in matrix.rows:
        for c in matrix.cols:
            mark = "y" if (r, c) in matrix.cells else "-"
            lines.append(f"{r}\t{c}\t{mark}")
    if matrix.gaps:
        lines.append("")
        lines.append("gaps: " + ", ".join(matrix.gaps))
    lines.append(f"coverage: {matrix.coverage_ratio:.2%}")
    return "\n".join(lines)


# ===========================================================================
# Template lint (delegates to C5)
# ===========================================================================


@kg_group.command("template-lint")
@_project_root_option
@click.option(
    "--all",
    "all_flag",
    is_flag=True,
    default=False,
    help="Lint every *.md.j2 found under template roots.",
)
def kg_template_lint(project_root: Path | None, all_flag: bool) -> None:
    """Static-check Jinja2 templates and embedded SPARQL queries."""
    from cataforge.kg.template_lint import lint_template_roots

    root = project_root or find_project_root()
    roots = _resolve_template_roots(root)
    if not roots:
        click.echo("no template roots found")
        return
    findings = lint_template_roots(roots, scan_all=all_flag)
    if not findings:
        click.echo("template-lint: clean")
        return
    for f in findings:
        click.echo(f"{f.path}:{f.line}: {f.rule_id}: {f.message}")
    raise click.exceptions.Exit(1)


# ===========================================================================
# Reasoning: infer / impact / explain
# ===========================================================================


@kg_group.command("infer")
@_project_root_option
@click.option(
    "--persist/--no-persist",
    "persist",
    default=True,
    help="Write derived triples to .doc-graph/inferred.nq (default: yes).",
)
def kg_infer(project_root: Path | None, persist: bool) -> None:
    """Materialise the limited-profile OWL-RL inference closure.

    Default profile: ``rdfs:subClassOf`` transitivity + instance
    propagation, ``owl:inverseOf`` symmetric materialisation, and
    ``owl:TransitiveProperty`` closure. The full design rationale —
    why these three and not more — is in design §1.6 + R-06."""
    from rdflib import Dataset

    from cataforge.kg.ontology import load_ontology
    from cataforge.kg.reasoning import infer
    from cataforge.kg.store import graph_dir_for

    store, root = _load_store(project_root)
    ontology = load_ontology(root, include_l3=True, strict=True)
    base_graph = _store_to_graph(store)
    derived = infer(base_graph, ontology)
    click.echo(f"derived triples: {len(derived)}")

    if persist:
        gdir = graph_dir_for(root)
        gdir.mkdir(parents=True, exist_ok=True)
        out_path = gdir / "inferred.nq"
        ds = Dataset()
        for s, p, o in derived:
            ds.default_graph.add((s, p, o))
        ds.serialize(destination=str(out_path), format="nquads")
        click.echo(f"wrote {out_path}")


@kg_group.command("impact")
@_project_root_option
@click.argument("node")
@click.option(
    "--depth",
    "depth",
    type=int,
    default=5,
    help="Advisory traversal depth (rdflib's + operator already terminates).",
)
def kg_impact(project_root: Path | None, node: str, depth: int) -> None:
    """List CURIE-shortened IRIs that transitively depend on NODE."""
    from cataforge.kg.query import impact

    store, _ = _load_store(project_root)
    deps = impact(store, node, max_depth=depth)
    if not deps:
        click.echo(f"no nodes depend on {node}")
        return
    for d in deps:
        click.echo(d)


@kg_group.command("explain")
@_project_root_option
@click.argument("subject")
@click.argument("predicate")
@click.argument("obj")
def kg_explain(
    project_root: Path | None,
    subject: str,
    predicate: str,
    obj: str,
) -> None:
    """Explain why (or whether) a triple holds in the (reasoned) store."""
    from cataforge.kg.query import explain

    store, _ = _load_store(project_root)
    result = explain(store, subject, predicate, obj)
    click.echo(f"derivation: {result.derivation}")
    if result.path:
        click.echo(f"path: {' → '.join(result.path)}")


# ===========================================================================
# Visualisation: cataforge kg viz
# ===========================================================================


@kg_group.command("viz")
@_project_root_option
@click.option(
    "--scope",
    "scope_class",
    default=None,
    help="Filter to instances of a class, e.g. cfa:Feature.",
)
@click.option(
    "--node",
    "root_node",
    default=None,
    help="Anchor the graph at a node (uses subgraph traversal).",
)
@click.option(
    "--depth",
    "depth",
    type=int,
    default=2,
    help="Traversal depth when --node is set.",
)
@click.option(
    "--format",
    "out_format",
    type=click.Choice(["mermaid", "dot", "svg"]),
    default="mermaid",
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write to file (default: stdout).",
)
def kg_viz(
    project_root: Path | None,
    scope_class: str | None,
    root_node: str | None,
    depth: int,
    out_format: str,
    out_path: Path | None,
) -> None:
    """Render the KG (or a subgraph) as mermaid / DOT / SVG.

    SVG requires the ``dot`` binary on PATH; if unavailable the
    DOT text is written instead and a stderr WARN is emitted.
    """
    from cataforge.kg.viz import (
        ViewSpec,
        render_dot,
        render_mermaid,
        render_svg,
    )

    store, _ = _load_store(project_root)
    spec = ViewSpec(
        scope_class=scope_class, root_node=root_node, depth=depth,
    )
    payload: bytes | str
    if out_format == "mermaid":
        payload = render_mermaid(store, spec)
    elif out_format == "dot":
        payload = render_dot(store, spec)
    else:
        try:
            payload = render_svg(store, spec)
        except FileNotFoundError:
            click.echo(
                "WARN: `dot` binary not found; falling back to DOT text",
                err=True,
            )
            payload = render_dot(store, spec)

    if out_path:
        out_path.write_bytes(
            payload if isinstance(payload, bytes) else payload.encode("utf-8"),
        )
        click.echo(f"wrote {out_path}", err=True)
    elif isinstance(payload, bytes):
        sys_stdout = click.get_text_stream("stdout").buffer
        sys_stdout.write(payload)
    else:
        click.echo(payload, nl=False)


# ===========================================================================
# Adapter dispatch surface
# ===========================================================================


@kg_group.group("adapter")
def kg_adapter_group() -> None:
    """List, inspect, and dispatch KG adapters (design §3)."""


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
@_project_root_option
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

    store, root = _load_store(project_root)
    config.setdefault("_project_root", str(root))
    adapter = cls(store=store, invocation_id=invocation_id, config=config)
    try:
        ctx = adapter.pre_dispatch_context(params)
    except AdapterError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(ctx, indent=2, ensure_ascii=False))


@kg_group.command("adapter-migrate")
@_project_root_option
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
@_project_root_option
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

    store, root = _load_store(project_root)
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


# ===========================================================================
# helpers
# ===========================================================================


def _expand_or_passthrough(token: str) -> str:
    from cataforge.kg.query import _expand_curie
    try:
        return _expand_curie(token)
    except ValueError:
        return token


def _coerce_set_value(raw: str) -> str | int | float | bool:
    if raw.lower() in {"true", "false"}:
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    # Strip surrounding quotes if present.
    if (raw.startswith('"') and raw.endswith('"')) or (
        raw.startswith("'") and raw.endswith("'")
    ):
        return raw[1:-1]
    return raw


_PREFIX_TO_SHORT: dict[str, str] = {}


def _shorten_triple(s: str, p: str, o: str) -> Any:
    from cataforge.kg.ontology import NAMESPACES
    from cataforge.kg.store import Triple
    global _PREFIX_TO_SHORT
    if not _PREFIX_TO_SHORT:
        _PREFIX_TO_SHORT = {iri: prefix for prefix, iri in NAMESPACES.items()}

    def short(iri: str) -> str:
        for full, prefix in _PREFIX_TO_SHORT.items():
            if iri.startswith(full):
                return f"{prefix}:{iri[len(full):]}"
        return iri
    return Triple(s=short(s), p=short(p), o=short(o))


def _to_graphml(store: Any) -> str:
    """Minimal GraphML export — nodes + edges, no attributes."""
    nodes: set[str] = set()
    edges: list[tuple[str, str, str]] = []
    for s, p, o, _ in store:
        nodes.add(s)
        if o.startswith(("http://", "https://")):
            nodes.add(o)
            edges.append((s, p, o))
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <graph id="kg" edgedefault="directed">',
    ]
    for n in sorted(nodes):
        parts.append(f'    <node id="{n}"/>')
    for i, (s, p, o) in enumerate(sorted(edges)):
        parts.append(
            f'    <edge id="e{i}" source="{s}" target="{o}" label="{p}"/>',
        )
    parts.append("  </graph>")
    parts.append("</graphml>")
    return "\n".join(parts) + "\n"


_SAFE_RE = __import__("re").compile(r"[^A-Za-z0-9_]")


def _safe(token: str) -> str:
    return str(_SAFE_RE.sub("_", token))
