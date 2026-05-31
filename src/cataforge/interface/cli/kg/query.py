"""cataforge kg read access — query, trace."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from cataforge.domain.kg import KnowledgeGraph
    from cataforge.domain.kg.trace import TraceChain

from cataforge.core.errors import (
    CataforgeError,
    KGQueryTimeoutError,
    KGStoreError,
)
from cataforge.core.paths import KG_STORE_REL
from cataforge.interface.cli.helpers import root_relative_default
from cataforge.interface.cli.kg import kg_group
from cataforge.interface.cli.kg._options import db_path_ro_option


@kg_group.command("query")
@click.argument("query_or_file")
@db_path_ro_option()
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["table", "json", "turtle"]),
    default="table",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--limit",
    type=int,
    default=100,
    show_default=True,
    help="Maximum rows for SELECT results.",
)
@click.option(
    "--timeout",
    type=float,
    default=30.0,
    show_default=True,
    help="Query timeout in seconds.",
)
@click.pass_context
def kg_query(
    ctx: click.Context,
    query_or_file: str,
    db_path: Path,
    output_fmt: str,
    limit: int,
    timeout: float,
) -> None:
    """Execute a SPARQL query against the KG store.

    QUERY_OR_FILE is a SPARQL string or a path to a .sparql file.
    """
    db_path = root_relative_default(ctx, "db_path", db_path, rel=KG_STORE_REL)

    from cataforge.domain.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraph

    sparql = _resolve_sparql_input(query_or_file)
    _guard_sparql_writes(sparql)
    sparql = _inject_limit(sparql, limit)

    config = KGConfig(store_backend="oxigraph", db_path=db_path)
    try:
        with KnowledgeGraph.connect(config) as kg:
            result_box: list[object] = []
            error_box: list[Exception] = []

            def _run_query() -> None:
                try:
                    raw = kg.store.query(sparql)
                    result_box.append(_materialize_query_result(raw))
                except Exception as exc:  # noqa: BLE001
                    error_box.append(exc)

            worker = threading.Thread(target=_run_query, daemon=True)
            worker.start()
            worker.join(timeout=timeout)

            if worker.is_alive():
                raise KGQueryTimeoutError(f"SPARQL query timed out after {timeout}s")
            if error_box:
                raise CataforgeError(f"SPARQL error: {error_box[0]}") from error_box[0]
            if not result_box:
                raise CataforgeError(
                    "SPARQL query returned no result (worker exited without populating result)"
                )

            _format_query_result(result_box[0], output_fmt)
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc


def _resolve_sparql_input(query_or_file: str) -> str:
    p = Path(query_or_file)
    if p.is_file():
        return p.read_text(encoding="utf-8").strip()
    return query_or_file


_SPARQL_WRITE_KEYWORDS = frozenset(
    ["UPDATE", "INSERT", "DELETE", "CLEAR", "DROP", "LOAD", "CREATE", "COPY", "MOVE", "ADD"]
)
_SPARQL_STRIP_RE = re.compile(
    r"(#[^\n]*\n|PREFIX\s+\S+\s*:\s*<[^>]*>\s*|BASE\s+<[^>]*>\s*)",
    re.IGNORECASE,
)


def _first_sparql_keyword(sparql: str) -> str:
    """Return the first operative keyword of a SPARQL string, upper-cased."""
    stripped = _SPARQL_STRIP_RE.sub("", sparql).lstrip()
    token = stripped.split()[0].upper() if stripped.split() else ""
    return token


def _guard_sparql_writes(sparql: str) -> None:
    """Raise CataforgeError when sparql contains a write operation."""
    keyword = _first_sparql_keyword(sparql)
    if keyword in _SPARQL_WRITE_KEYWORDS:
        raise CataforgeError(
            "SPARQL writes are not supported via 'kg query' — "
            "use 'kg add/update/delete' or a transaction script"
        )


def _inject_limit(sparql: str, limit: int) -> str:
    upper = sparql.upper()
    if "SELECT" in upper and "LIMIT" not in upper:
        return f"{sparql.rstrip().rstrip(';')} LIMIT {limit}"
    return sparql


def _materialize_query_result(raw: object) -> object:
    """Consume pyoxigraph lazy iterators into thread-safe Python objects."""
    type_name = type(raw).__name__
    if type_name == "QueryBoolean" or isinstance(raw, bool):
        return ("ask", bool(raw))
    if type_name == "QuerySolutions":
        variables_terms = list(raw.variables)  # type: ignore[union-attr]
        variables = [str(v).lstrip("?") for v in variables_terms]
        rows: list[dict[str, str]] = []
        for row in raw:  # type: ignore[arg-type]
            record: dict[str, str] = {}
            for raw_v, name in zip(variables_terms, variables, strict=True):
                try:
                    val = row[raw_v]
                except (KeyError, IndexError):
                    val = None
                record[name] = _term_to_str(val)
            rows.append(record)
        return ("select", variables, rows)
    if type_name == "QueryTriples":
        triples = [
            {
                "subject": t.subject,
                "predicate": t.predicate,
                "object": t.object,
            }
            for t in raw  # type: ignore[arg-type]
        ]
        return ("construct", triples)
    return ("select", [], [])


def _format_query_result(result: object, fmt: str) -> None:
    kind = result[0]  # type: ignore[index]
    if kind == "ask":
        _format_ask_result(result[1], fmt)  # type: ignore[index]
    elif kind == "select":
        _format_select_result(result[1], result[2], fmt)  # type: ignore[index]
    elif kind == "construct":
        _format_construct_result(result[1], fmt)  # type: ignore[index]


def _format_ask_result(value: bool, fmt: str) -> None:
    if fmt == "json":
        click.echo(json.dumps({"result": value}))
    else:
        click.echo("true" if value else "false")


def _format_select_result(variables: list[str], rows_data: list[dict[str, str]], fmt: str) -> None:
    if fmt == "json":
        click.echo(json.dumps(rows_data, indent=2, ensure_ascii=False))
        return

    if not rows_data:
        click.echo("(no results)")
        return

    col_widths = {v: len(v) for v in variables}
    for row in rows_data:
        for v in variables:
            col_widths[v] = max(col_widths[v], len(row.get(v, "")))

    header = "  ".join(v.ljust(col_widths[v]) for v in variables)
    separator = "  ".join("-" * col_widths[v] for v in variables)
    click.echo(header)
    click.echo(separator)
    for row in rows_data:
        line = "  ".join(row.get(v, "").ljust(col_widths[v]) for v in variables)
        click.echo(line)


def _format_construct_result(triples: list[dict[str, object]], fmt: str) -> None:
    if fmt == "json":
        out = [
            {
                "subject": _term_to_str(t["subject"]),
                "predicate": _term_to_str(t["predicate"]),
                "object": _term_to_str(t["object"]),
            }
            for t in triples
        ]
        click.echo(json.dumps(out, indent=2, ensure_ascii=False))
        return

    if fmt == "turtle":
        for t in triples:
            click.echo(
                f"{_ntriples_term(t['subject'])} "
                f"{_ntriples_term(t['predicate'])} "
                f"{_ntriples_term(t['object'])} ."
            )
        return

    col_widths = {"subject": 7, "predicate": 9, "object": 6}
    rows = []
    for t in triples:
        row = {
            "subject": _term_to_str(t["subject"]),
            "predicate": _term_to_str(t["predicate"]),
            "object": _term_to_str(t["object"]),
        }
        for k in col_widths:
            col_widths[k] = max(col_widths[k], len(row[k]))
        rows.append(row)

    header = "  ".join(k.ljust(col_widths[k]) for k in ("subject", "predicate", "object"))
    separator = "  ".join("-" * col_widths[k] for k in ("subject", "predicate", "object"))
    click.echo(header)
    click.echo(separator)
    for row in rows:
        line = "  ".join(row[k].ljust(col_widths[k]) for k in ("subject", "predicate", "object"))
        click.echo(line)


def _term_to_str(term: object) -> str:
    if term is None:
        return ""
    return str(getattr(term, "value", term))


def _ntriples_term(term: object) -> str:
    if term is None:
        return '""'
    type_name = type(term).__name__
    if type_name == "NamedNode":
        return f"<{term.value}>"  # type: ignore[union-attr]
    if type_name == "Literal":
        escaped = term.value.replace("\\", "\\\\").replace('"', '\\"')  # type: ignore[union-attr]
        return f'"{escaped}"'
    if type_name == "BlankNode":
        return f"_:{term.value}"  # type: ignore[union-attr]
    return f"<{term}>"


# ------------------------------------------------------------------
# kg trace
# ------------------------------------------------------------------


@kg_group.command("trace")
@click.argument("entity_id", required=False, default=None)
@db_path_ro_option()
@click.option(
    "--direction",
    type=click.Choice(["downstream", "upstream", "both"]),
    default="downstream",
    show_default=True,
    help="Chain traversal direction.",
)
@click.option(
    "--coverage",
    is_flag=True,
    default=False,
    help=(
        "Without ENTITY_ID: show the global Feature coverage matrix. "
        "With ENTITY_ID: append coverage detail to the trace chain."
    ),
)
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["table", "json", "mermaid"]),
    default="table",
    show_default=True,
    help="Output format.",
)
@click.pass_context
def kg_trace(
    ctx: click.Context,
    entity_id: str | None,
    db_path: Path,
    direction: str,
    coverage: bool,
    output_fmt: str,
) -> None:
    """Trace the dependency chain from a business entity.

    When called with --coverage and no ENTITY_ID, prints a global
    Feature coverage matrix instead of a single-entity chain.
    """
    db_path = root_relative_default(ctx, "db_path", db_path, rel=KG_STORE_REL)

    from cataforge.domain.kg import KGConfig, KGStoreNotInitializedError, KnowledgeGraph

    config = KGConfig(store_backend="oxigraph", db_path=db_path)

    if coverage and entity_id is None:
        try:
            with KnowledgeGraph.connect(config) as kg:
                _coverage_matrix(kg, output_fmt)
        except KGStoreNotInitializedError as exc:
            raise KGStoreError(str(exc)) from exc
        return

    if entity_id is None:
        raise CataforgeError("ENTITY_ID is required (or use --coverage for global matrix).")

    try:
        with KnowledgeGraph.connect(config) as kg:
            if not kg.query.exists(entity_id):
                raise CataforgeError(f"Entity not found: {entity_id}")

            chain = kg.trace.from_requirement(entity_id, direction=direction)  # type: ignore[arg-type]

            coverage_detail = None
            if coverage:
                coverage_detail = kg.trace.coverage(entity_id)

            if output_fmt == "json":
                _trace_json(chain, coverage_detail)
            elif output_fmt == "mermaid":
                _trace_mermaid(chain, kg)
            else:
                _trace_table(chain, kg, coverage_detail)
    except KGStoreNotInitializedError as exc:
        raise KGStoreError(str(exc)) from exc


def _coverage_matrix(kg: KnowledgeGraph, fmt: str) -> None:
    rows = kg.trace.bidirectional_coverage()

    if fmt == "json":
        out = [
            {
                "feature_id": r.feature_id,
                "title": r.title,
                "has_impl": r.has_impl,
                "has_test": r.has_test,
            }
            for r in rows
        ]
        click.echo(json.dumps(out, indent=2, ensure_ascii=False))
        return

    if not rows:
        click.echo("(no features found)")
        return

    id_w = max(len("Feature"), max(len(r.feature_id) for r in rows))
    title_w = max(len("Title"), max(len(r.title or "") for r in rows))
    click.echo(f"{'Feature':<{id_w}}  {'Title':<{title_w}}  Impl?  Test?")
    click.echo(f"{'-' * id_w}  {'-' * title_w}  -----  -----")
    for r in rows:
        impl = "yes" if r.has_impl else "no"
        test = "yes" if r.has_test else "no"
        click.echo(f"{r.feature_id:<{id_w}}  {(r.title or ''):<{title_w}}  {impl:<5}  {test:<5}")


def _trace_json(chain: object, coverage_detail: dict | None) -> None:
    import dataclasses

    d = dataclasses.asdict(chain)  # type: ignore[arg-type]
    if coverage_detail is not None:
        d["coverage_detail"] = coverage_detail
    click.echo(json.dumps(d, indent=2, ensure_ascii=False))


def _chain_buckets(chain: TraceChain) -> list[tuple[str, list[str]]]:
    return [
        ("requirements", chain.requirements),
        ("acceptance_criteria", chain.acceptance_criteria),
        ("modules", chain.modules),
        ("components", chain.components),
        ("tasks", chain.tasks),
        ("test_cases", chain.test_cases),
        ("review_reports", chain.review_reports),
    ]


def _trace_table(chain: TraceChain, kg: KnowledgeGraph, coverage_detail: dict | None) -> None:
    click.echo(f"Traceability chain from {chain.root_id} (coverage={chain.coverage_status})")
    click.echo()

    buckets = _chain_buckets(chain)
    layer_w = max(len("Layer"), max((len(b[0]) for b in buckets), default=5))
    click.echo(f"{'Layer':<{layer_w}}  {'Entity ID':<12}  Title")
    click.echo(f"{'-' * layer_w}  {'-' * 12}  {'-' * 30}")

    root_entity = kg.query.entity(chain.root_id)
    root_title = root_entity.get("title", "") if root_entity else ""
    root_class = root_entity.get("_class", "root") if root_entity else "root"
    click.echo(f"{root_class:<{layer_w}}  {chain.root_id:<12}  {root_title}")

    for layer_name, ids in buckets:
        for eid in ids:
            if eid == chain.root_id:
                continue
            entity = kg.query.entity(eid)
            title = entity.get("title", "") if entity else ""
            click.echo(f"{layer_name:<{layer_w}}  {eid:<12}  {title}")

    if coverage_detail:
        click.echo()
        status = coverage_detail.get("status", "unknown")
        impl = "yes" if coverage_detail.get("has_impl") else "no"
        test = "yes" if coverage_detail.get("has_test") else "no"
        click.echo(f"Coverage: status={status} impl={impl} test={test}")


def _trace_mermaid(chain: TraceChain, kg: KnowledgeGraph) -> None:
    click.echo("graph TD")

    buckets = _chain_buckets(chain)

    all_ids: list[str] = [chain.root_id]
    seen = {chain.root_id}
    for _, ids in buckets:
        for eid in ids:
            if eid not in seen:
                all_ids.append(eid)
                seen.add(eid)

    for eid in all_ids:
        entity = kg.query.entity(eid)
        title = entity.get("title", "") if entity else ""
        safe_label = title.replace('"', "'")
        click.echo(f'    {eid}["{eid}: {safe_label}"]')

    bucket_map = {name: ids for name, ids in buckets}
    for src_layer, dst_layer, rel in _MERMAID_EDGE_MAP:
        src_ids = bucket_map.get(src_layer, [])
        dst_ids = bucket_map.get(dst_layer, [])
        if src_ids and dst_ids:
            for s in src_ids:
                for d in dst_ids:
                    click.echo(f"    {s} -->|{rel}| {d}")

    downstream_ids = [eid for eid in all_ids if eid != chain.root_id]
    if downstream_ids and not any(
        bucket_map.get(src) and bucket_map.get(dst) for src, dst, _ in _MERMAID_EDGE_MAP
    ):
        for d in downstream_ids:
            click.echo(f"    {chain.root_id} --> {d}")


_MERMAID_EDGE_MAP = [
    ("requirements", "modules", "implements"),
    ("requirements", "components", "implements"),
    ("modules", "tasks", "decomposes"),
    ("acceptance_criteria", "test_cases", "verifies"),
    ("requirements", "acceptance_criteria", "validates"),
]
