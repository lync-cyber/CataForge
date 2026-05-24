"""CLI tests for the Wave C ``cataforge kg *`` subcommands.

Uses Click's ``CliRunner`` so we exercise the real Click app object
without spinning up a subprocess. The wheel-install e2e suite under
``tests/e2e/`` covers the user-facing install path separately."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli.main import cli
from cataforge.kg.store import (
    INSTANCES_FILENAME,
    RDFLibStore,
    Triple,
    graph_dir_for,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def empty_project(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    return tmp_path


@pytest.fixture
def project_with_data(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([
        Triple("cfa:prd/F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd/F-001", "cfk:hasId", "F-001"),
        Triple("cfa:prd/F-001", "rdfs:label", "login"),
        Triple("cfa:prd/F-001", "cfk:definedIn", "cfk:doc/prd"),
        Triple("cfa:test/TC-001", "rdf:type", "cfa:TestCase"),
        Triple("cfa:test/TC-001", "cfk:hasId", "TC-001"),
        Triple("cfa:test/TC-001", "cfa:validates", "cfa:prd/F-001"),
    ])
    store.persist()
    return tmp_path


# ---------- init ----------

def test_kg_init_creates_empty_graph(runner: CliRunner, empty_project: Path) -> None:
    result = runner.invoke(
        cli, ["kg", "init", "--project-root", str(empty_project)],
    )
    assert result.exit_code == 0
    assert (graph_dir_for(empty_project) / INSTANCES_FILENAME).is_file()


# ---------- query ----------

def test_kg_query_sparql_emits_jsonlines(
    runner: CliRunner, project_with_data: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "query", "--project-root", str(project_with_data),
        "--sparql", "SELECT ?id WHERE { ?x cfk:hasId ?id } ORDER BY ?id",
    ])
    assert result.exit_code == 0
    rows = [json.loads(ln) for ln in result.output.strip().splitlines()]
    ids = [r["id"] for r in rows]
    assert "F-001" in ids
    assert "TC-001" in ids


def test_kg_query_dsl(
    runner: CliRunner, project_with_data: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "query", "--project-root", str(project_with_data),
        "--dsl", '{"rel": "cfa:validates"}',
    ])
    assert result.exit_code == 0
    assert "TC-001" in result.output or "test/TC-001" in result.output


def test_kg_query_cypher(
    runner: CliRunner, project_with_data: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "query", "--project-root", str(project_with_data),
        "--cypher", "MATCH (a:TestCase)-[:validates]->(b:Feature) RETURN a, b",
    ])
    assert result.exit_code == 0
    assert "TC-001" in result.output


def test_kg_query_rejects_multiple_sources(
    runner: CliRunner, project_with_data: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "query", "--project-root", str(project_with_data),
        "--sparql", "ASK { ?x ?p ?o }",
        "--dsl", '{"rel": "cfa:implements"}',
    ])
    assert result.exit_code != 0
    assert "exactly one" in result.output


def test_kg_query_rejects_no_source(
    runner: CliRunner, project_with_data: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "query", "--project-root", str(project_with_data),
    ])
    assert result.exit_code != 0


# ---------- validate ----------

def test_kg_validate_conforming_data(
    runner: CliRunner, project_with_data: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "validate", "--project-root", str(project_with_data),
    ])
    # Conformance not asserted — but the command must run and report something.
    assert "conforms:" in result.output
    assert "violations:" in result.output


# ---------- entity / relation CRUD ----------

def test_kg_add_then_get_entity(
    runner: CliRunner, empty_project: Path,
) -> None:
    add = runner.invoke(cli, [
        "kg", "add-entity", "--project-root", str(empty_project),
        "--type", "cfa:Feature", "--id", "F-001",
        "--iri", "cfa:prd/F-001",
        "--props", '{"rdfs:label": "login"}',
    ])
    assert add.exit_code == 0
    get = runner.invoke(cli, [
        "kg", "get-entity", "--project-root", str(empty_project),
        "cfa:prd/F-001",
    ])
    assert get.exit_code == 0
    assert "login" in get.output


def test_kg_update_entity_replaces_value(
    runner: CliRunner, project_with_data: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "update-entity", "--project-root", str(project_with_data),
        "cfa:prd/F-001", "--set", "cfa:status=active",
    ])
    assert result.exit_code == 0
    get = runner.invoke(cli, [
        "kg", "get-entity", "--project-root", str(project_with_data),
        "cfa:prd/F-001",
    ])
    assert "active" in get.output


def test_kg_delete_entity_removes_all_predicates(
    runner: CliRunner, project_with_data: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "delete-entity", "--project-root", str(project_with_data),
        "cfa:prd/F-001",
    ])
    assert result.exit_code == 0
    get = runner.invoke(cli, [
        "kg", "get-entity", "--project-root", str(project_with_data),
        "cfa:prd/F-001",
    ])
    # No triples left → empty stdout (plus maybe a blank line).
    assert get.output.strip() == ""


def test_kg_add_then_remove_relation(
    runner: CliRunner, empty_project: Path,
) -> None:
    add = runner.invoke(cli, [
        "kg", "add-relation", "--project-root", str(empty_project),
        "cfa:arch/M-001", "cfa:realizes", "cfa:prd/F-001",
    ])
    assert add.exit_code == 0
    rm = runner.invoke(cli, [
        "kg", "remove-relation", "--project-root", str(empty_project),
        "cfa:arch/M-001", "cfa:realizes", "cfa:prd/F-001",
    ])
    assert rm.exit_code == 0
    assert "removed 1" in rm.output


# ---------- ingest ----------

def test_kg_ingest_single_file(
    runner: CliRunner, empty_project: Path,
) -> None:
    md = empty_project / "docs" / "prd.md"
    md.write_text(textwrap.dedent("""\
        ---
        id: prd-x
        ---
        # PRD-X
        ## F-001 login
    """), encoding="utf-8")
    result = runner.invoke(cli, [
        "kg", "ingest", "--project-root", str(empty_project),
        "--file", str(md),
    ])
    assert result.exit_code == 0
    assert "applied" in result.output


def test_kg_ingest_all_delegates_to_migrate(
    runner: CliRunner, empty_project: Path,
) -> None:
    (empty_project / "docs" / "prd.md").write_text(textwrap.dedent("""\
        ---
        id: prd-x
        ---
        # PRD-X
        ## F-001 login
    """), encoding="utf-8")
    result = runner.invoke(cli, [
        "kg", "ingest", "--project-root", str(empty_project), "--all",
    ])
    assert result.exit_code == 0
    assert "files processed" in result.output


# ---------- export ----------

def test_kg_export_turtle(
    runner: CliRunner, project_with_data: Path,
) -> None:
    out = project_with_data / "export.ttl"
    result = runner.invoke(cli, [
        "kg", "export", "--project-root", str(project_with_data),
        "--format", "turtle", "--out", str(out),
    ])
    assert result.exit_code == 0
    assert out.is_file()
    txt = out.read_text(encoding="utf-8")
    assert "cfk:hasId" in txt or "hasId" in txt


def test_kg_export_graphml(
    runner: CliRunner, project_with_data: Path,
) -> None:
    out = project_with_data / "export.graphml"
    result = runner.invoke(cli, [
        "kg", "export", "--project-root", str(project_with_data),
        "--format", "graphml", "--out", str(out),
    ])
    assert result.exit_code == 0
    assert "<graphml" in out.read_text(encoding="utf-8")


# ---------- render ----------

def test_kg_render_check_uses_poc_templates(
    runner: CliRunner, project_with_data: Path,
) -> None:
    """``kg render --check`` walks the dogfood template dir; smoke test
    that the PoC templates remain idempotent against the test fixture."""
    # Copy PoC templates into the project (mirrors deploy layout).
    repo_root = Path(__file__).resolve().parents[2]
    src_tpl = repo_root / ".cataforge" / "skills" / "doc-gen" / "templates" / "standard"
    dst_tpl = (
        project_with_data / ".cataforge" / "skills" / "doc-gen"
        / "templates" / "standard"
    )
    dst_tpl.mkdir(parents=True)
    for f in src_tpl.glob("*.md.j2"):
        (dst_tpl / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")

    result = runner.invoke(cli, [
        "kg", "render", "--project-root", str(project_with_data), "--check",
    ])
    assert result.exit_code == 0, result.output
    assert "prd.md.j2: OK" in result.output


def test_kg_render_single_doc_to_stdout(
    runner: CliRunner, project_with_data: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src_tpl = repo_root / ".cataforge" / "skills" / "doc-gen" / "templates" / "standard"
    dst_tpl = (
        project_with_data / ".cataforge" / "skills" / "doc-gen"
        / "templates" / "standard"
    )
    dst_tpl.mkdir(parents=True)
    (dst_tpl / "prd.md.j2").write_text(
        (src_tpl / "prd.md.j2").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = runner.invoke(cli, [
        "kg", "render", "--project-root", str(project_with_data),
        "--doc", "cfk:doc/prd", "--template", "prd.md.j2",
        "--project", "acme",
    ])
    assert result.exit_code == 0
    assert "F-001: login" in result.output


# ---------- coverage ----------

def test_kg_coverage_preset_rtm_table(
    runner: CliRunner, project_with_data: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "coverage", "--project-root", str(project_with_data),
        "--preset", "rtm",
    ])
    assert result.exit_code == 0
    assert "coverage:" in result.output


def test_kg_coverage_explicit_args_markdown(
    runner: CliRunner, project_with_data: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "coverage", "--project-root", str(project_with_data),
        "--rows", "cfa:Feature",
        "--cols", "cfa:TestCase",
        "--via", "cfa:validates",
        "--format", "markdown",
    ])
    assert result.exit_code == 0
    assert "| row \\ col |" in result.output


def test_kg_coverage_requires_preset_or_full_triple(
    runner: CliRunner, project_with_data: Path,
) -> None:
    result = runner.invoke(cli, [
        "kg", "coverage", "--project-root", str(project_with_data),
    ])
    assert result.exit_code != 0
    assert "preset" in result.output


# ---------- template-lint ----------

def test_kg_template_lint_clean_on_poc_templates(
    runner: CliRunner, project_with_data: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    src_tpl = repo_root / ".cataforge" / "skills" / "doc-gen" / "templates" / "standard"
    dst_tpl = (
        project_with_data / ".cataforge" / "skills" / "doc-gen"
        / "templates" / "standard"
    )
    dst_tpl.mkdir(parents=True)
    for f in src_tpl.glob("*.md.j2"):
        (dst_tpl / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    result = runner.invoke(cli, [
        "kg", "template-lint", "--project-root", str(project_with_data),
    ])
    assert result.exit_code == 0
    assert "clean" in result.output
