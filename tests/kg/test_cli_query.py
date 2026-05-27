"""`cataforge kg query` CLI tests (backlog C1).

Exercises SPARQL query execution against an in-memory KG store
pre-loaded with the waterfall vertical-slice fixture (9 entities,
4 traceability relations). Tests cover SELECT / ASK / CONSTRUCT
result types across table / json / turtle output formats.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pyoxigraph_installed = importlib.util.find_spec("pyoxigraph") is not None
linkml_runtime_installed = importlib.util.find_spec("linkml_runtime") is not None

pytestmark = pytest.mark.skipif(
    not (pyoxigraph_installed and linkml_runtime_installed),
    reason="kg extra not installed (pyoxigraph + linkml-runtime)",
)


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _cli():
    from cataforge.cli.main import _register_commands, cli

    _register_commands()
    return cli


def _init_and_ingest(tmp_path: Path) -> Path:
    """Create an oxigraph store and ingest the waterfall fixture. Return db path."""
    from click.testing import CliRunner

    db = tmp_path / "store"
    runner = CliRunner()

    init = runner.invoke(_cli(), ["kg", "init", "--db-path", str(db)])
    assert init.exit_code == 0, init.output

    imp = runner.invoke(
        _cli(),
        [
            "kg", "import",
            "--project-root", str(FIXTURE_ROOT / "waterfall"),
            "--db-path", str(db),
        ],
    )
    assert imp.exit_code == 0, imp.output
    return db


# ------------------------------------------------------------------
# SELECT queries
# ------------------------------------------------------------------


class TestSelectTable:
    def test_select_returns_entity_rows(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        sparql = (
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "SELECT ?eid WHERE { ?s cf:entity_id ?eid } ORDER BY ?eid"
        )
        result = CliRunner().invoke(
            _cli(), ["kg", "query", "--db-path", str(db), sparql],
        )
        assert result.exit_code == 0, result.output
        assert "eid" in result.output
        for eid in ("AC-001", "AC-002", "F-001", "F-002",
                     "M-001", "M-002", "TC-001", "TC-002"):
            assert eid in result.output

    def test_select_limit_caps_rows(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        sparql = (
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "SELECT ?eid WHERE { ?s cf:entity_id ?eid } ORDER BY ?eid"
        )
        result = CliRunner().invoke(
            _cli(),
            ["kg", "query", "--db-path", str(db),
             "--output", "json", "--limit", "3", sparql],
        )
        assert result.exit_code == 0, result.output
        rows = json.loads(result.output)
        assert len(rows) == 3


class TestSelectJson:
    def test_json_output_is_parseable_list(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        sparql = (
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "SELECT ?eid ?title WHERE { "
            "  ?s cf:entity_id ?eid ; cf:title ?title "
            "} ORDER BY ?eid"
        )
        result = CliRunner().invoke(
            _cli(),
            ["kg", "query", "--db-path", str(db), "--output", "json", sparql],
        )
        assert result.exit_code == 0, result.output
        rows = json.loads(result.output)
        assert isinstance(rows, list)
        assert len(rows) == 9
        eids = {r["eid"] for r in rows}
        assert eids == {"AC-001", "AC-002", "F-001", "F-002",
                        "M-001", "M-002", "TC-001", "TC-002",
                        "tech-stack-arch"}
        assert all("title" in r for r in rows)

    def test_json_limit_caps_result(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        sparql = (
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "SELECT ?eid WHERE { ?s cf:entity_id ?eid } ORDER BY ?eid"
        )
        result = CliRunner().invoke(
            _cli(),
            ["kg", "query", "--db-path", str(db),
             "--output", "json", "--limit", "2", sparql],
        )
        assert result.exit_code == 0, result.output
        rows = json.loads(result.output)
        assert len(rows) == 2


# ------------------------------------------------------------------
# ASK queries
# ------------------------------------------------------------------


class TestAsk:
    def test_ask_true_returns_true(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        sparql = (
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            'ASK { ?s cf:entity_id "F-001" }'
        )
        result = CliRunner().invoke(
            _cli(), ["kg", "query", "--db-path", str(db), sparql],
        )
        assert result.exit_code == 0, result.output
        assert result.output.strip() == "true"

    def test_ask_false_returns_false(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        sparql = (
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            'ASK { ?s cf:entity_id "NONEXISTENT-999" }'
        )
        result = CliRunner().invoke(
            _cli(), ["kg", "query", "--db-path", str(db), sparql],
        )
        assert result.exit_code == 0, result.output
        assert result.output.strip() == "false"

    def test_ask_json_format(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        sparql = (
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            'ASK { ?s cf:entity_id "F-001" }'
        )
        result = CliRunner().invoke(
            _cli(),
            ["kg", "query", "--db-path", str(db), "--output", "json", sparql],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload == {"result": True}


# ------------------------------------------------------------------
# CONSTRUCT queries
# ------------------------------------------------------------------


class TestConstruct:
    def test_construct_turtle_output(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        sparql = (
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "CONSTRUCT { ?s cf:entity_id ?eid } "
            "WHERE { ?s cf:entity_id ?eid } "
        )
        result = CliRunner().invoke(
            _cli(),
            ["kg", "query", "--db-path", str(db), "--output", "turtle", sparql],
        )
        assert result.exit_code == 0, result.output
        assert "entity_id" in result.output
        assert "F-001" in result.output

    def test_construct_json_output(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        sparql = (
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "CONSTRUCT { ?s cf:entity_id ?eid } "
            "WHERE { ?s cf:entity_id ?eid } "
        )
        result = CliRunner().invoke(
            _cli(),
            ["kg", "query", "--db-path", str(db), "--output", "json", sparql],
        )
        assert result.exit_code == 0, result.output
        triples = json.loads(result.output)
        assert isinstance(triples, list)
        assert len(triples) == 9
        assert all({"subject", "predicate", "object"} <= set(t) for t in triples)


# ------------------------------------------------------------------
# File input
# ------------------------------------------------------------------


class TestFileInput:
    def test_sparql_file_is_read_and_executed(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        sparql_file = tmp_path / "features.sparql"
        sparql_file.write_text(
            "PREFIX cf: <https://cataforge.dev/ontology/>\n"
            "SELECT ?eid WHERE { ?s a cf:Feature ; cf:entity_id ?eid } "
            "ORDER BY ?eid\n",
            encoding="utf-8",
        )
        result = CliRunner().invoke(
            _cli(),
            ["kg", "query", "--db-path", str(db), "--output", "json",
             str(sparql_file)],
        )
        assert result.exit_code == 0, result.output
        rows = json.loads(result.output)
        eids = [r["eid"] for r in rows]
        assert eids == ["F-001", "F-002"]


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------


class TestErrors:
    def test_sparql_syntax_error_exits_nonzero(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "query", "--db-path", str(db), "NOT VALID SPARQL AT ALL"],
        )
        assert result.exit_code != 0

    def test_uninitialised_store_exits_nonzero(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = tmp_path / "nonexistent"
        result = CliRunner().invoke(
            _cli(),
            ["kg", "query", "--db-path", str(db),
             "PREFIX cf: <https://cataforge.dev/ontology/> "
             "SELECT ?s WHERE { ?s ?p ?o } LIMIT 1"],
        )
        assert result.exit_code != 0
