"""Unit tests for :mod:`cataforge.kg.migrate` — one-shot doc-index → KG."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli.main import cli
from cataforge.kg.migrate import (
    BACKUP_DIRNAME_PREFIX,
    MigrationError,
    migrate,
)
from cataforge.kg.store import (
    INSTANCES_FILENAME,
    META_FILENAME,
    RDFLibStore,
    graph_dir_for,
)


def _write_doc(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _write_index(root: Path, file_paths: list[str]) -> None:
    docs = {
        f"doc-{i}": {"file_path": fp}
        for i, fp in enumerate(file_paths)
    }
    index = {"version": "1", "documents": docs}
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / ".doc-index.json").write_text(
        json.dumps(index), encoding="utf-8",
    )


def test_migrate_writes_instances_and_meta(tmp_path: Path) -> None:
    _write_doc(tmp_path, "docs/prd.md", """\
        ---
        id: prd-x
        ---
        # PRD-X

        ## F-001 login
        """)
    _write_index(tmp_path, ["docs/prd.md"])
    report = migrate(tmp_path, validate=False)
    assert report.files_processed == 1
    assert report.triples_written > 0
    gdir = graph_dir_for(tmp_path)
    assert (gdir / INSTANCES_FILENAME).is_file()
    assert (gdir / META_FILENAME).is_file()


def test_orphan_doc_counted_as_skipped(tmp_path: Path) -> None:
    _write_doc(tmp_path, "docs/no-id.md", "# Just a heading\n")
    _write_index(tmp_path, ["docs/no-id.md"])
    report = migrate(tmp_path, validate=False)
    assert report.files_processed == 0
    assert report.files_skipped == 1
    assert "no-id.md" in report.skipped_files[0]


def test_missing_index_falls_back_to_glob(tmp_path: Path) -> None:
    _write_doc(tmp_path, "docs/prd.md", """\
        ---
        id: prd-x
        ---
        # PRD-X
        """)
    # No .doc-index.json on purpose.
    report = migrate(tmp_path, validate=False)
    assert report.files_processed == 1


def test_existing_graph_backed_up(tmp_path: Path) -> None:
    _write_doc(tmp_path, "docs/prd.md", """\
        ---
        id: prd-x
        ---
        # PRD-X
        """)
    _write_index(tmp_path, ["docs/prd.md"])
    migrate(tmp_path, validate=False)  # first migration creates the graph
    report = migrate(tmp_path, validate=False)  # second one must back it up
    assert report.backup_path is not None
    assert report.backup_path.name.startswith(BACKUP_DIRNAME_PREFIX)


def test_rollback_restores_previous_graph(tmp_path: Path) -> None:
    _write_doc(tmp_path, "docs/prd.md", """\
        ---
        id: prd-x
        ---
        # PRD-X

        ## F-001 login
        """)
    _write_index(tmp_path, ["docs/prd.md"])

    migrate(tmp_path, validate=False)
    first_count = sum(1 for _ in _store_iter(tmp_path))

    # Add another item, re-migrate (more triples, old graph rotated to .bak)
    _write_doc(tmp_path, "docs/prd.md", """\
        ---
        id: prd-x
        ---
        # PRD-X

        ## F-001 login
        ## F-002 signup
        """)
    migrate(tmp_path, validate=False)
    second_count = sum(1 for _ in _store_iter(tmp_path))
    assert second_count > first_count

    # Now rollback — the old graph (only F-001) must come back.
    rb_report = migrate(tmp_path, rollback=True, validate=False)
    assert rb_report.rolled_back_from is not None
    restored_count = sum(1 for _ in _store_iter(tmp_path))
    assert restored_count == first_count


def test_rollback_with_no_backups_raises(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    with pytest.raises(MigrationError, match="No backups"):
        migrate(tmp_path, rollback=True)


def test_cross_doc_relation_resolved(tmp_path: Path) -> None:
    _write_doc(tmp_path, "docs/prd.md", """\
        ---
        id: prd-x
        ---
        # PRD-X

        ## F-001 login
        """)
    _write_doc(tmp_path, "docs/arch.md", """\
        ---
        id: arch-x
        realizes: F-001
        ---
        # Arch-X

        ## M-001 auth
        """)
    _write_index(tmp_path, ["docs/prd.md", "docs/arch.md"])
    migrate(tmp_path, validate=False)

    rows = _query(
        tmp_path,
        "PREFIX cfa: <https://cataforge.dev/ontology/artifact#>\n"
        "SELECT ?s ?o WHERE { ?s cfa:realizes ?o }",
    )
    assert any(
        r["s"].endswith("doc/arch-x") and r["o"].endswith("prd-x/F-001")
        for r in rows
    )


def test_shacl_validation_runs_when_enabled(tmp_path: Path) -> None:
    _write_doc(tmp_path, "docs/prd.md", """\
        ---
        id: prd-x
        ---
        # PRD-X

        ## F-001 login
        """)
    _write_index(tmp_path, ["docs/prd.md"])
    report = migrate(tmp_path, validate=True)
    # Validation ran — shacl_report_text is non-empty whether or not it conformed.
    assert report.shacl_report_text != ""


def test_format_summary_renders_counts(tmp_path: Path) -> None:
    _write_doc(tmp_path, "docs/prd.md", """\
        ---
        id: prd-x
        ---
        # PRD-X
        """)
    _write_index(tmp_path, ["docs/prd.md"])
    report = migrate(tmp_path, validate=False)
    text = report.format()
    assert "files processed : 1" in text
    assert "triples written" in text


def test_kg_migrate_cli_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["kg", "migrate", "--help"])
    assert result.exit_code == 0
    assert "rollback" in result.output


def _store_iter(root: Path):
    store = RDFLibStore()
    store.load(root)
    yield from store


def _query(root: Path, sparql: str):
    store = RDFLibStore()
    store.load(root)
    return store.query(sparql)
