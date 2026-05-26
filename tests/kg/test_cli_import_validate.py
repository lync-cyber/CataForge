"""`cataforge kg import` + `cataforge kg validate` CLI smoke."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

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


def test_kg_import_memory_backend(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        _cli(),
        [
            "kg",
            "import",
            "--project-root",
            str(FIXTURE_ROOT / "waterfall"),
            "--backend",
            "memory",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    stats = json.loads(result.output)
    assert stats["parsed_docs"] == 3
    assert stats["extracted_entities"] == 8
    assert stats["extracted_relations"] == 4
    assert stats["entities_written"] == 8
    assert stats["relations_written"] == 4
    assert stats["verify_ok"] is True


def test_kg_import_dry_run_exits_zero(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        _cli(),
        [
            "kg",
            "import",
            "--project-root",
            str(FIXTURE_ROOT / "agile"),
            "--backend",
            "memory",
            "--dry-run",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    stats = json.loads(result.output)
    assert stats["dry_run"] is True
    assert stats["entities_written"] == 0
    assert stats["relations_written"] == 0


def test_kg_import_then_validate_oxigraph_backend(tmp_path: Path) -> None:
    db = tmp_path / "store"
    runner = CliRunner()

    init = runner.invoke(
        _cli(), ["kg", "init", "--db-path", str(db), "--backend", "oxigraph"]
    )
    assert init.exit_code == 0, init.output

    imp = runner.invoke(
        _cli(),
        [
            "kg",
            "import",
            "--project-root",
            str(FIXTURE_ROOT / "waterfall"),
            "--db-path",
            str(db),
            "--backend",
            "oxigraph",
        ],
    )
    assert imp.exit_code == 0, imp.output

    val = runner.invoke(
        _cli(), ["kg", "validate", "--db-path", str(db), "--json"]
    )
    assert val.exit_code == 0, val.output
    report = json.loads(val.output)
    assert report["ok"] is True
    assert report["violations"] == []
