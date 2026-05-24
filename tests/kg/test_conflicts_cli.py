"""``cataforge kg conflicts`` + ``kg resolve`` CLI surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli.main import cli
from cataforge.kg.delta import (
    Conflict,
    DeltaReport,
    write_conflict_files,
)
from cataforge.kg.store import RDFLibStore, Triple, graph_dir_for


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project_with_conflict(tmp_path: Path) -> Path:
    """A project with one Feature and one pre-queued conflict file."""
    (tmp_path / "docs").mkdir()
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([
        Triple("cfa:prd/F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd/F-001", "cfk:hasId", "F-001"),
        Triple("cfa:prd/F-001", "rdfs:label", "kg-label"),
    ])
    store.persist()

    report = DeltaReport(conflicts=[Conflict(
        subject="cfa:prd/F-001",
        predicate="rdfs:label",
        kg_value="kg-label",
        file_value="file-label",
        render_value=None,
    )])
    write_conflict_files(report, project_root=tmp_path, doc_id="prd")
    return tmp_path


# ---------- write_conflict_files ----------

def test_write_conflict_files_creates_one_per_conflict(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    report = DeltaReport(conflicts=[
        Conflict(
            subject="cfa:prd/F-001", predicate="rdfs:label",
            kg_value="a", file_value="b", render_value=None,
        ),
        Conflict(
            subject="cfa:prd/F-002", predicate="cfa:status",
            kg_value="draft", file_value="active", render_value=None,
        ),
    ])
    written = write_conflict_files(report, project_root=tmp_path)
    assert len(written) == 2
    for path in written:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "resolution_options" in payload
        assert payload["conflict_id"].startswith("c_")


def test_write_conflict_files_empty_report_writes_nothing(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    written = write_conflict_files(DeltaReport(), project_root=tmp_path)
    assert written == []


# ---------- kg conflicts ----------

def test_kg_conflicts_lists_pending(
    runner: CliRunner, project_with_conflict: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "conflicts", "--project-root", str(project_with_conflict),
    ])
    assert result.exit_code == 0, result.output
    assert "cfa:prd/F-001" in result.output
    assert "kg-label" in result.output
    assert "file-label" in result.output


def test_kg_conflicts_empty_dir_is_friendly(
    runner: CliRunner, tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    result = runner.invoke(cli, [
        "kg", "conflicts", "--project-root", str(tmp_path),
    ])
    assert result.exit_code == 0
    assert "no conflicts" in result.output


# ---------- kg resolve ----------

def test_kg_resolve_pick_file_replaces_kg_value(
    runner: CliRunner, project_with_conflict: Path,
) -> None:
    cdir = graph_dir_for(project_with_conflict) / "conflicts"
    conflict_id = next(iter(cdir.glob("*.json"))).name.split("_")[-1].replace(".json", "")

    result = runner.invoke(cli, [
        "kg", "resolve", "--project-root", str(project_with_conflict),
        conflict_id, "--pick", "file",
    ])
    assert result.exit_code == 0, result.output

    # Conflict file consumed.
    assert not list(cdir.glob(f"*{conflict_id}*"))

    # Store now carries the file value.
    store = RDFLibStore()
    store.load(project_with_conflict)
    labels = [
        o for s, p, o, _ in store
        if "F-001" in s and "label" in p
    ]
    assert "file-label" in labels
    assert "kg-label" not in labels


def test_kg_resolve_pick_merge_requires_value(
    runner: CliRunner, project_with_conflict: Path,
) -> None:
    cdir = graph_dir_for(project_with_conflict) / "conflicts"
    conflict_id = next(iter(cdir.glob("*.json"))).name.split("_")[-1].replace(".json", "")
    result = runner.invoke(cli, [
        "kg", "resolve", "--project-root", str(project_with_conflict),
        conflict_id, "--pick", "merge",
    ])
    assert result.exit_code != 0
    assert "requires --value" in result.output


def test_kg_resolve_unknown_id_fails(
    runner: CliRunner, project_with_conflict: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "resolve", "--project-root", str(project_with_conflict),
        "c_no_such_id", "--pick", "kg",
    ])
    assert result.exit_code != 0
    assert "no conflict found" in result.output


def test_kg_resolve_corrupt_json_fails_cleanly(
    runner: CliRunner, project_with_conflict: Path,
) -> None:
    """A corrupt conflict file must surface as a ClickException, not a
    bare JSONDecodeError traceback. Regression for kg_cmd.py kg_resolve
    where json.loads was uncaught."""
    cdir = graph_dir_for(project_with_conflict) / "conflicts"
    conflict_path = next(iter(cdir.glob("*.json")))
    conflict_id = conflict_path.name.split("_")[-1].replace(".json", "")
    conflict_path.write_text("{this is not json", encoding="utf-8")

    result = runner.invoke(cli, [
        "kg", "resolve", "--project-root", str(project_with_conflict),
        conflict_id, "--pick", "kg",
    ])
    assert result.exit_code != 0
    assert "not valid JSON" in result.output
    # No raw traceback in output.
    assert "Traceback" not in result.output
