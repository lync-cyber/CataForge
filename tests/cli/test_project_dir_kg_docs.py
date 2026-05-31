"""The global ``--project-dir`` must reach the docs/kg subcommands.

These command groups carry their own ``--project-root`` / ``--db-path``
options whose relative defaults resolved against the process cwd, so a
``cataforge --project-dir <X> kg init`` / ``docs index`` silently wrote to
the cwd-discovered project instead of ``<X>``. ``root_relative_default``
now routes the global flag through when the local option is defaulted,
while an explicit local value still wins.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cataforge.interface.cli.main import cli


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / ".cataforge").mkdir(parents=True)
    (root / ".cataforge" / "framework.json").write_text(
        json.dumps({"version": "0.1.0"}), encoding="utf-8"
    )
    return root


def _elsewhere(tmp_path: Path, monkeypatch) -> Path:
    cwd = tmp_path / "elsewhere"
    cwd.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(cwd)
    return cwd


def test_docs_index_honours_project_dir(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path)
    docs = root / "docs"
    docs.mkdir()
    (docs / "note.md").write_text(
        "---\nid: note\ndoc_type: prd\nauthor: x\nstatus: draft\ndeps: []\n---\n# Note\n",
        encoding="utf-8",
    )
    cwd = _elsewhere(tmp_path, monkeypatch)

    result = CliRunner().invoke(cli, ["--project-dir", str(root), "docs", "index"])
    assert result.exit_code == 0, result.output

    assert (root / "docs" / ".doc-index.json").is_file()
    assert not (cwd / "docs" / ".doc-index.json").exists()


def test_kg_init_honours_project_dir(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path)
    cwd = _elsewhere(tmp_path, monkeypatch)

    result = CliRunner().invoke(cli, ["--project-dir", str(root), "kg", "init"])
    assert result.exit_code == 0, result.output

    assert (root / ".cataforge" / "kg" / "store").exists()
    assert not (cwd / ".cataforge" / "kg" / "store").exists()


def test_kg_init_explicit_db_path_overrides_project_dir(tmp_path: Path, monkeypatch) -> None:
    root = _project(tmp_path)
    _elsewhere(tmp_path, monkeypatch)
    explicit = tmp_path / "explicit-store"

    result = CliRunner().invoke(
        cli, ["--project-dir", str(root), "kg", "init", "--db-path", str(explicit)]
    )
    assert result.exit_code == 0, result.output

    assert explicit.exists()
    assert not (root / ".cataforge" / "kg" / "store").exists()
