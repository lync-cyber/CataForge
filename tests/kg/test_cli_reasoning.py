"""CLI tests for ``cataforge kg infer / impact / explain / viz`` (Wave E1+E2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli.main import cli
from cataforge.kg.store import RDFLibStore, Triple, graph_dir_for


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def chain_project(tmp_path: Path) -> Path:
    """Project with a 3-link cfa:dependsOn chain to exercise transitivity."""
    (tmp_path / "docs").mkdir()
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([
        Triple("cfa:m/A", "rdf:type", "cfa:Module"),
        Triple("cfa:m/B", "rdf:type", "cfa:Module"),
        Triple("cfa:m/C", "rdf:type", "cfa:Module"),
        Triple("cfa:m/A", "cfa:dependsOn", "cfa:m/B"),
        Triple("cfa:m/B", "cfa:dependsOn", "cfa:m/C"),
    ])
    store.persist()
    return tmp_path


@pytest.fixture
def inverse_project(tmp_path: Path) -> Path:
    """Project with cfa:implements only (lets us check inverse explain)."""
    (tmp_path / "docs").mkdir()
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([
        Triple("cfa:m/M1", "rdf:type", "cfa:Module"),
        Triple("cfa:m/M1", "cfa:implements", "cfa:f/F1"),
        Triple("cfa:f/F1", "rdf:type", "cfa:Feature"),
    ])
    store.persist()
    return tmp_path


# ---------- infer ----------

def test_kg_infer_materialises_transitive_closure(
    runner: CliRunner, chain_project: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "infer", "--project-root", str(chain_project),
    ])
    assert result.exit_code == 0, result.output
    # A → B → C means we expect at least 1 derived triple (A → C).
    assert "derived triples:" in result.output
    inferred = graph_dir_for(chain_project) / "inferred.nq"
    assert inferred.is_file()
    body = inferred.read_text(encoding="utf-8")
    assert "dependsOn" in body
    assert "/C" in body and "/A" in body


def test_kg_infer_no_persist_skips_file(
    runner: CliRunner, chain_project: Path,
) -> None:
    inferred = graph_dir_for(chain_project) / "inferred.nq"
    inferred.unlink(missing_ok=True)
    result = runner.invoke(cli, [
        "kg", "infer", "--project-root", str(chain_project),
        "--no-persist",
    ])
    assert result.exit_code == 0, result.output
    assert not inferred.is_file()


# ---------- impact ----------

def test_kg_impact_returns_dependents(
    runner: CliRunner, chain_project: Path,
) -> None:
    """C is the deepest leaf — A and B both transitively depend on it."""
    # First materialise the closure so cfa:dependsOn+ has chains.
    runner.invoke(cli, [
        "kg", "infer", "--project-root", str(chain_project), "--no-persist",
    ])
    result = runner.invoke(cli, [
        "kg", "impact", "--project-root", str(chain_project), "cfa:m/C",
    ])
    assert result.exit_code == 0, result.output
    # Both A and B should appear (B directly, A transitively).
    assert "cfa:m/A" in result.output
    assert "cfa:m/B" in result.output


def test_kg_impact_empty_returns_message(
    runner: CliRunner, chain_project: Path,
) -> None:
    """A is the top of the chain — nothing depends on it."""
    result = runner.invoke(cli, [
        "kg", "impact", "--project-root", str(chain_project), "cfa:m/A",
    ])
    assert result.exit_code == 0
    assert "no nodes depend on" in result.output


# ---------- explain ----------

def test_kg_explain_base_triple(
    runner: CliRunner, inverse_project: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "explain", "--project-root", str(inverse_project),
        "cfa:m/M1", "cfa:implements", "cfa:f/F1",
    ])
    assert result.exit_code == 0, result.output
    assert "derivation: base" in result.output


def test_kg_explain_absent_triple(
    runner: CliRunner, inverse_project: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "explain", "--project-root", str(inverse_project),
        "cfa:m/M99", "cfa:implements", "cfa:f/F99",
    ])
    assert result.exit_code == 0
    assert "derivation: absent" in result.output


# ---------- viz ----------

def test_kg_viz_mermaid_default(
    runner: CliRunner, chain_project: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "viz", "--project-root", str(chain_project),
    ])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("graph LR")
    # Each chain link shows up as an edge.
    assert "dependsOn" in result.output


def test_kg_viz_dot(
    runner: CliRunner, chain_project: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "viz", "--project-root", str(chain_project),
        "--format", "dot",
    ])
    assert result.exit_code == 0, result.output
    assert "digraph kg" in result.output


def test_kg_viz_scope_filter(
    runner: CliRunner, chain_project: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "viz", "--project-root", str(chain_project),
        "--scope", "cfa:Module",
        "--format", "mermaid",
    ])
    assert result.exit_code == 0, result.output


def test_kg_viz_writes_to_file(
    runner: CliRunner, chain_project: Path,
) -> None:
    out_path = chain_project / "graph.mmd"
    result = runner.invoke(cli, [
        "kg", "viz", "--project-root", str(chain_project),
        "--out", str(out_path),
    ])
    assert result.exit_code == 0, result.output
    assert out_path.is_file()
    body = out_path.read_text(encoding="utf-8")
    assert "graph LR" in body
