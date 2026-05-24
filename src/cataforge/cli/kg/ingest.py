"""``cataforge kg`` content → graph commands: ingest, migrate, export, render, etc.

All commands decorate the ``kg_group`` defined in ``cataforge.cli.kg_cmd``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from cataforge.cli.kg._common import (
    load_store,
    project_root_option,
    resolve_template_roots,
    shorten_triple,
    to_graphml,
)
from cataforge.cli.kg_cmd import kg_group
from cataforge.core.paths import find_project_root

# ---- benchmark ----------------------------------------------------------


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


# ---- migrate ------------------------------------------------------------


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
    help="Restore docs/.doc-graph/ from the most recent migration backup.",
)
@click.option(
    "--validate/--no-validate",
    "validate",
    default=False,
    help="Run SHACL validation after migration completes (WARN-only).",
)
def kg_migrate(
    project_root: Path | None,
    rollback: bool,
    validate: bool,
) -> None:
    """Big-bang ingest every docs/**/*.md into the graph (idempotent).

    With ``--rollback`` restores the most recent ``.doc-graph.backup-*/``
    snapshot — useful when an unexpected migration result needs to be
    undone before re-running with different shape graphs.
    """
    from cataforge.kg.migrate import migrate
    from cataforge.kg.migrate import rollback as do_rollback

    root = project_root or find_project_root()
    if rollback:
        restored = do_rollback(root)
        if restored is None:
            raise click.ClickException("no backup found under docs/.doc-graph.backup-*")
        click.echo(f"restored from {restored}")
        return
    report = migrate(root, validate=validate)
    click.echo(report.format())


# ---- ingest -------------------------------------------------------------


@kg_group.command("ingest")
@project_root_option
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
    every error is swallowed and exit code is forced to 0.
    """
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
    store, _ = load_store(root)
    result = ingest_markdown(file_path, project_root=root)
    if result.document is None:
        click.echo(f"skipped {file_path}: no frontmatter id")
        return
    scope = {result.document.iri} | {it.iri for it in result.items}
    kg_triples = [
        shorten_triple(s, p, o) for s, p, o, _ in store
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


# ---- export -------------------------------------------------------------


@kg_group.command("export")
@project_root_option
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
    store, _ = load_store(project_root)
    if out_format == "graphml":
        out_path.write_text(to_graphml(store), encoding="utf-8")
    else:
        rdflib_format = {"jsonld": "json-ld", "nquads": "nquads"}.get(
            out_format, out_format,
        )
        data = store._dataset.serialize(format=rdflib_format)  # noqa: SLF001
        out_path.write_text(str(data), encoding="utf-8")
    click.echo(f"wrote {out_path}")


# ---- render -------------------------------------------------------------


@kg_group.command("render")
@project_root_option
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

    store, root = load_store(project_root)
    template_roots = resolve_template_roots(root)
    if not template_roots:
        default_root = (
            root / ".cataforge" / "skills" / "doc-gen" / "templates" / "standard"
        )
        raise click.ClickException(
            f"no template root found (tried {[str(default_root)]})",
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


# ---- template lint ------------------------------------------------------


@kg_group.command("template-lint")
@project_root_option
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
    roots = resolve_template_roots(root)
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
