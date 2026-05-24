"""Unit tests for the benchmark harness — focus on the API surface, not
on actual wall-clock measurements (those would flap across CI hosts)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cataforge.cli.main import cli
from cataforge.kg.benchmark import (
    DEFAULT_BUDGET,
    BenchmarkResult,
    format_report,
    load_budget,
    synth_triples,
)


def test_synth_triples_count() -> None:
    triples = list(synth_triples(100))
    assert len(triples) == 100


def test_synth_triples_covers_all_kinds() -> None:
    triples = list(synth_triples(8))
    preds = {t.p for t in triples}
    assert "rdf:type" in preds
    assert "rdfs:label" in preds
    assert "cfa:implements" in preds


def test_load_budget_default_when_path_none() -> None:
    assert load_budget(None) == DEFAULT_BUDGET


def test_load_budget_default_when_file_missing(tmp_path: Path) -> None:
    assert load_budget(tmp_path / "nonexistent.json") == DEFAULT_BUDGET


def test_load_budget_parses_file(tmp_path: Path) -> None:
    cfg = {"single_sparql_query": {"max_ms": 99}}
    p = tmp_path / "budget.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    assert load_budget(p) == cfg


def test_benchmark_result_status_ok() -> None:
    r = BenchmarkResult(name="x", elapsed_ms=50.0, budget_ms=100.0, detail="-")
    assert r.status == "OK"


def test_benchmark_result_status_warn() -> None:
    r = BenchmarkResult(name="x", elapsed_ms=150.0, budget_ms=100.0, detail="-")
    assert r.status == "WARN"


def test_benchmark_result_status_info_when_no_budget() -> None:
    r = BenchmarkResult(name="x", elapsed_ms=50.0, budget_ms=None, detail="-")
    assert r.status == "INFO"


def test_format_report_includes_metric_names() -> None:
    results = [
        BenchmarkResult(
            name="full_rebuild", elapsed_ms=10.0,
            budget_ms=2000.0, detail="-",
        ),
    ]
    report = format_report(results, budget=DEFAULT_BUDGET)
    assert "full_rebuild" in report
    assert "OK" in report


def test_kg_benchmark_cli_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["kg", "benchmark", "--help"])
    assert result.exit_code == 0
    assert "performance-budget" in result.output
