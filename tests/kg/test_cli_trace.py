"""`cataforge kg trace` CLI tests (backlog C2).

Exercises traceability chain queries against an in-memory KG store
pre-loaded with the waterfall vertical-slice fixture. The fixture has:
  - F-001, F-002 (Feature)
  - AC-001, AC-002 (AcceptanceCriteria)
  - M-001 implements F-001, M-002 implements F-002 (Module)
  - TC-001 verifies AC-001, TC-002 verifies AC-002 (TestCase)

Tests cover: downstream/upstream trace, table/json/mermaid output,
global --coverage matrix, and error paths.
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
# Downstream trace
# ------------------------------------------------------------------


class TestDownstream:
    def test_table_shows_root_and_downstream_entities(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "trace", "--db-path", str(db), "F-001"],
        )
        assert result.exit_code == 0, result.output
        assert "F-001" in result.output
        assert "M-001" in result.output

    def test_json_contains_chain_structure(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "trace", "--db-path", str(db), "--output", "json", "F-001"],
        )
        assert result.exit_code == 0, result.output
        chain = json.loads(result.output)
        assert chain["root_id"] == "F-001"
        assert "M-001" in chain["modules"]
        assert chain["coverage_status"] in ("full", "partial", "none")
        assert isinstance(chain["chain_breaks"], list)

    def test_downstream_f002_reaches_m002(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "trace", "--db-path", str(db), "--output", "json", "F-002"],
        )
        assert result.exit_code == 0, result.output
        chain = json.loads(result.output)
        assert chain["root_id"] == "F-002"
        assert "M-002" in chain["modules"]


# ------------------------------------------------------------------
# Upstream trace
# ------------------------------------------------------------------


class TestUpstream:
    def test_upstream_from_module_finds_feature(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "trace", "--db-path", str(db),
             "--direction", "upstream", "--output", "json", "M-001"],
        )
        assert result.exit_code == 0, result.output
        chain = json.loads(result.output)
        assert chain["root_id"] == "M-001"
        assert "F-001" in chain["requirements"]


class TestBothDirections:
    def test_both_merges_up_and_downstream(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "trace", "--db-path", str(db),
             "--direction", "both", "--output", "json", "M-001"],
        )
        assert result.exit_code == 0, result.output
        chain = json.loads(result.output)
        assert "F-001" in chain["requirements"]


# ------------------------------------------------------------------
# Mermaid output
# ------------------------------------------------------------------


class TestMermaid:
    def test_mermaid_contains_graph_syntax(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "trace", "--db-path", str(db), "--output", "mermaid", "F-001"],
        )
        assert result.exit_code == 0, result.output
        assert "graph TD" in result.output
        assert "F-001" in result.output
        assert "M-001" in result.output
        assert "-->" in result.output

    def test_mermaid_node_labels_include_title(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "trace", "--db-path", str(db), "--output", "mermaid", "F-001"],
        )
        assert result.exit_code == 0, result.output
        assert "F-001" in result.output


# ------------------------------------------------------------------
# Global coverage matrix (--coverage without entity_id)
# ------------------------------------------------------------------


class TestGlobalCoverage:
    def test_coverage_table_lists_all_features(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "trace", "--db-path", str(db), "--coverage"],
        )
        assert result.exit_code == 0, result.output
        assert "F-001" in result.output
        assert "F-002" in result.output

    def test_coverage_json_has_structured_rows(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "trace", "--db-path", str(db),
             "--coverage", "--output", "json"],
        )
        assert result.exit_code == 0, result.output
        rows = json.loads(result.output)
        assert isinstance(rows, list)
        assert len(rows) == 2
        by_id = {r["feature_id"]: r for r in rows}
        assert "F-001" in by_id
        assert "F-002" in by_id
        assert isinstance(by_id["F-001"]["has_impl"], bool)
        assert isinstance(by_id["F-001"]["has_test"], bool)
        assert by_id["F-001"]["has_impl"] is True
        assert by_id["F-002"]["has_impl"] is True


# ------------------------------------------------------------------
# Coverage flag with a specific entity
# ------------------------------------------------------------------


class TestCoverageWithEntity:
    def test_coverage_appended_to_chain_json(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "trace", "--db-path", str(db),
             "--coverage", "--output", "json", "F-001"],
        )
        assert result.exit_code == 0, result.output
        chain = json.loads(result.output)
        assert chain["root_id"] == "F-001"
        assert "coverage_detail" in chain
        assert chain["coverage_detail"]["has_impl"] is True


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------


class TestErrors:
    def test_nonexistent_entity_exits_nonzero(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = _init_and_ingest(tmp_path)
        result = CliRunner().invoke(
            _cli(),
            ["kg", "trace", "--db-path", str(db), "NONEXISTENT-999"],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_uninitialised_store_exits_nonzero(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        db = tmp_path / "nonexistent"
        result = CliRunner().invoke(
            _cli(),
            ["kg", "trace", "--db-path", str(db), "F-001"],
        )
        assert result.exit_code != 0
