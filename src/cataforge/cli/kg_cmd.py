"""cataforge kg — knowledge-graph CLI surface.

Wave A ships only the ``benchmark`` subcommand; subsequent waves attach
``init``, ``migrate``, ``query``, ``validate``, ``render``, ``ingest``,
``infer``, ``viz``, and ``adapter-*`` per design note §2.5.
"""

from __future__ import annotations

from pathlib import Path

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
