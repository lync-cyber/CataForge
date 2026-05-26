"""`cataforge kg init` CLI smoke (sub-PR 2 deliverable)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from click.testing import CliRunner

pyoxigraph_installed = importlib.util.find_spec("pyoxigraph") is not None
linkml_runtime_installed = importlib.util.find_spec("linkml_runtime") is not None

pytestmark = pytest.mark.skipif(
    not (pyoxigraph_installed and linkml_runtime_installed),
    reason="kg extra not installed (pyoxigraph + linkml-runtime)",
)


def _import_cli():
    from cataforge.cli.main import _register_commands, cli

    _register_commands()
    return cli


def test_kg_init_memory_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(_import_cli(), ["kg", "init", "--backend", "memory"])
    assert result.exit_code == 0, result.output
    assert "OK:" in result.output
    assert "rdfs:subClassOf" in result.output


def test_kg_init_oxigraph_writes_to_db_path(tmp_path: Path) -> None:
    runner = CliRunner()
    db = tmp_path / "store"
    result = runner.invoke(
        _import_cli(),
        ["kg", "init", "--backend", "oxigraph", "--db-path", str(db)],
    )
    assert result.exit_code == 0, result.output
    assert db.is_dir()
    assert any(db.iterdir())


def test_kg_init_refuses_existing_store_without_force(tmp_path: Path) -> None:
    runner = CliRunner()
    db = tmp_path / "store"
    cli_obj = _import_cli()

    first = runner.invoke(cli_obj, ["kg", "init", "--db-path", str(db)])
    assert first.exit_code == 0, first.output

    second = runner.invoke(cli_obj, ["kg", "init", "--db-path", str(db)])
    assert second.exit_code != 0
    assert "already exists" in second.output


def test_kg_init_force_overwrites(tmp_path: Path) -> None:
    runner = CliRunner()
    db = tmp_path / "store"
    cli_obj = _import_cli()

    runner.invoke(cli_obj, ["kg", "init", "--db-path", str(db)])
    second = runner.invoke(cli_obj, ["kg", "init", "--db-path", str(db), "--force"])
    assert second.exit_code == 0, second.output
