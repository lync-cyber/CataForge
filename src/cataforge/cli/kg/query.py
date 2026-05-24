"""``cataforge kg`` read commands: query, validate, conflicts, coverage, viz, reasoning.

All commands decorate the ``kg_group`` defined in ``cataforge.cli.kg_cmd``.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from cataforge.cli.kg._common import (
    format_coverage,
    load_store,
    project_root_option,
    store_to_graph,
)
from cataforge.cli.kg_cmd import kg_group
from cataforge.core.paths import find_project_root

# ---- query --------------------------------------------------------------


@kg_group.command("query")
@project_root_option
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
    store, _ = load_store(project_root)
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


# ---- validate -----------------------------------------------------------


@kg_group.command("validate")
@project_root_option
@click.option(
    "--shape",
    "shape_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="External SHACL shapes file (defaults to bundled L0/L1/L2 + L3).",
)
def kg_validate(project_root: Path | None, shape_file: Path | None) -> None:
    """Run SHACL validation against the bundled (or external) shape graph.

    Exit code reflects conformance: 0 on conforms, 1 on violation.
    """
    from cataforge.kg.ontology import load_shapes
    from cataforge.kg.reasoning import validate as reasoning_validate
    from cataforge.kg.store import graph_dir_for

    store, root = load_store(project_root)
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


# ---- conflicts (list + resolve) ----------------------------------------


@kg_group.command("conflicts")
@project_root_option
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
@project_root_option
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
    try:
        payload = json.loads(target_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(
            f"conflict file {target_path.name} is not valid JSON: {exc.msg}",
        ) from exc

    store, _ = load_store(root)
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


# ---- coverage -----------------------------------------------------------


@kg_group.command("coverage")
@project_root_option
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

    store, _ = load_store(project_root)
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
    click.echo(format_coverage(matrix, out_format))


# ---- reasoning: infer / impact / explain --------------------------------


@kg_group.command("infer")
@project_root_option
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
    why these three and not more — is in design §1.6 + R-06.
    """
    from rdflib import Dataset

    from cataforge.kg.ontology import load_ontology
    from cataforge.kg.reasoning import infer
    from cataforge.kg.store import graph_dir_for

    store, root = load_store(project_root)
    ontology = load_ontology(root, include_l3=True, strict=True)
    base_graph = store_to_graph(store)
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
@project_root_option
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

    store, _ = load_store(project_root)
    deps = impact(store, node, max_depth=depth)
    if not deps:
        click.echo(f"no nodes depend on {node}")
        return
    for d in deps:
        click.echo(d)


@kg_group.command("explain")
@project_root_option
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

    store, _ = load_store(project_root)
    result = explain(store, subject, predicate, obj)
    click.echo(f"derivation: {result.derivation}")
    if result.path:
        click.echo(f"path: {' → '.join(result.path)}")


# ---- visualisation ------------------------------------------------------


@kg_group.command("viz")
@project_root_option
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

    store, _ = load_store(project_root)
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
