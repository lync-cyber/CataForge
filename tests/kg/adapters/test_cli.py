"""``cataforge kg adapter *`` CLI surface — list / show / context / write-back."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli.main import cli
from cataforge.kg.store import RDFLibStore, Triple


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    return tmp_path


@pytest.fixture
def project_with_feature(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([
        Triple("cfk:doc/prd-acme", "rdf:type", "cfk:Document"),
        Triple("cfa:prd-acme/F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd-acme/F-001", "cfk:hasId", "F-001"),
        Triple("cfa:prd-acme/F-001", "rdfs:label", "login"),
        Triple("cfa:prd-acme/F-001", "cfk:definedIn", "cfk:doc/prd-acme"),
    ])
    store.persist()
    return tmp_path


# ---------- list ----------

def test_adapter_list_shows_all_builtins(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["kg", "adapter", "list"])
    assert result.exit_code == 0, result.output
    for name in (
        "feature_authoring", "module_implements",
        "task_decompose", "test_validates",
        "doc_read", "ui_renders",
    ):
        assert name in result.output


# ---------- show ----------

def test_adapter_show_emits_json_with_config_schema(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["kg", "adapter", "show", "feature_authoring"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["name"] == "feature_authoring"
    assert payload["config_schema"]["required"] == [
        "pre_dispatch_queries", "write_back_schema",
    ]


def test_adapter_show_unknown_fails(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["kg", "adapter", "show", "no-such-adapter"])
    assert result.exit_code != 0
    assert "no adapter registered" in result.output


# ---------- context ----------

def test_adapter_context_runs_pre_dispatch_queries(
    runner: CliRunner, project_with_feature: Path,
) -> None:
    config = {
        "pre_dispatch_queries": {
            "existing_features": (
                "SELECT ?id WHERE {"
                " ?f a cfa:Feature ; cfk:hasId ?id ;"
                " cfk:definedIn $doc_iri "
                "} ORDER BY ?id"
            ),
        },
        "write_back_schema": "ignored.json",
    }
    config_path = project_with_feature / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = runner.invoke(cli, [
        "kg", "adapter", "context", "feature_authoring",
        "--project-root", str(project_with_feature),
        "--config", str(config_path),
        "--params", json.dumps({"doc_iri": "cfk:doc/prd-acme"}),
    ])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["existing_features"] == [{"id": "F-001"}]


# ---------- write-back ----------

def test_adapter_writeback_persists_triples(
    runner: CliRunner, project: Path,
) -> None:
    schema_path = project / "feature.schema.json"
    schema_path.write_text(json.dumps({
        "items": [{
            "from": "features",
            "iri": "cfa:${doc_id}/${id}",
            "type": "cfa:Feature",
            "literals": {"cfk:hasId": "id", "rdfs:label": "label"},
            "iri_refs": {"cfk:definedIn": "cfk:doc/${doc_id}"},
        }]
    }), encoding="utf-8")
    config_path = project / "config.json"
    config_path.write_text(json.dumps({
        "pre_dispatch_queries": {},
        "write_back_schema": str(schema_path),
    }), encoding="utf-8")
    output_path = project / "output.json"
    output_path.write_text(json.dumps({
        "doc_id": "prd-acme",
        "features": [{"id": "F-001", "label": "Login"}],
    }), encoding="utf-8")

    result = runner.invoke(cli, [
        "kg", "adapter", "write-back", "feature_authoring",
        "--project-root", str(project),
        "--config", str(config_path),
        "--output", str(output_path),
        "--invocation-id", "test-inv-1",
    ])
    assert result.exit_code == 0, result.output
    assert "wrote back" in result.output

    # Reload the store and confirm the named graph survived persist().
    store = RDFLibStore()
    store.load(project)
    quads = [
        (s, p, o, g) for s, p, o, g in store
        if s.endswith("prd-acme/F-001")
    ]
    assert quads
    assert any(g and "test-inv-1" in g for _, _, _, g in quads)
