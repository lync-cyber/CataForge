"""Unit tests for :mod:`cataforge.kg.ontology`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdflib import Graph

from cataforge.kg.ontology import (
    BUILTIN_ONTOLOGY_FILES,
    BUILTIN_SHAPE_FILES,
    NAMESPACES,
    OntologyError,
    bind_namespaces,
    builtin_ttl_path,
    load_framework_kg_config,
    load_ontology,
)


def test_namespaces_contain_required_prefixes() -> None:
    for prefix in ("cfk", "cfp", "cfa", "rdf", "rdfs", "owl", "xsd", "sh"):
        assert prefix in NAMESPACES


def test_store_uses_same_namespace_table() -> None:
    # store.py imports NAMESPACES as _BUILTIN_PREFIXES — there must not be
    # two divergent prefix tables.
    from cataforge.kg.store import _BUILTIN_PREFIXES
    assert _BUILTIN_PREFIXES is NAMESPACES


def test_bind_namespaces_on_graph() -> None:
    g = Graph()
    bind_namespaces(g)
    bound = {p for p, _ in g.namespace_manager.namespaces()}
    assert set(NAMESPACES).issubset(bound)


def test_builtin_ttl_paths_exist() -> None:
    for stem in BUILTIN_ONTOLOGY_FILES + BUILTIN_SHAPE_FILES:
        path = builtin_ttl_path(stem)
        assert path.is_file()


def test_load_framework_kg_config_missing(tmp_project: Path) -> None:
    assert load_framework_kg_config(tmp_project) == {}


def test_load_framework_kg_config_parses(tmp_project: Path) -> None:
    cfg_dir = tmp_project / ".cataforge"
    cfg_dir.mkdir()
    (cfg_dir / "framework.json").write_text(
        json.dumps({"kg": {"namespaces": {"myproj": "https://x.io/o#"}}}),
        encoding="utf-8",
    )
    cfg = load_framework_kg_config(tmp_project)
    assert cfg == {"namespaces": {"myproj": "https://x.io/o#"}}


def test_load_framework_kg_config_invalid_json(tmp_project: Path) -> None:
    cfg_dir = tmp_project / ".cataforge"
    cfg_dir.mkdir()
    (cfg_dir / "framework.json").write_text("{ broken", encoding="utf-8")
    with pytest.raises(OntologyError):
        load_framework_kg_config(tmp_project)


def test_load_framework_kg_config_kg_not_object(tmp_project: Path) -> None:
    cfg_dir = tmp_project / ".cataforge"
    cfg_dir.mkdir()
    (cfg_dir / "framework.json").write_text(
        json.dumps({"kg": "oops"}), encoding="utf-8",
    )
    with pytest.raises(OntologyError):
        load_framework_kg_config(tmp_project)


def test_l3_namespace_shadow_rejected(tmp_project: Path) -> None:
    cfg_dir = tmp_project / ".cataforge"
    cfg_dir.mkdir()
    (cfg_dir / "framework.json").write_text(
        json.dumps({"kg": {"namespaces": {"cfk": "https://shadow.io/"}}}),
        encoding="utf-8",
    )
    with pytest.raises(OntologyError, match="conflicts with built-in"):
        load_ontology(tmp_project, include_l3=True, strict=True)


def test_l3_namespace_attached(tmp_project: Path) -> None:
    cfg_dir = tmp_project / ".cataforge"
    cfg_dir.mkdir()
    (cfg_dir / "framework.json").write_text(
        json.dumps({"kg": {"namespaces": {"saas": "https://x.io/saas#"}}}),
        encoding="utf-8",
    )
    g = load_ontology(tmp_project, include_l3=True, strict=True)
    bound = dict(g.namespace_manager.namespaces())
    assert "saas" in bound


def test_l3_ontology_file_missing(tmp_project: Path) -> None:
    cfg_dir = tmp_project / ".cataforge"
    cfg_dir.mkdir()
    (cfg_dir / "framework.json").write_text(
        json.dumps({"kg": {"ontology_files": [".cataforge/ontology/none.ttl"]}}),
        encoding="utf-8",
    )
    with pytest.raises(OntologyError, match="not found"):
        load_ontology(tmp_project, include_l3=True, strict=True)


def test_l3_ontology_file_loaded(tmp_project: Path) -> None:
    cfg_dir = tmp_project / ".cataforge"
    cfg_dir.mkdir()
    onto_dir = cfg_dir / "ontology"
    onto_dir.mkdir()
    (onto_dir / "myproj.ttl").write_text(
        "@prefix myproj: <https://x.io/myproj#> .\n"
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "myproj:Persona a owl:Class .\n",
        encoding="utf-8",
    )
    (cfg_dir / "framework.json").write_text(
        json.dumps({
            "kg": {
                "namespaces": {"myproj": "https://x.io/myproj#"},
                "ontology_files": [".cataforge/ontology/myproj.ttl"],
            },
        }),
        encoding="utf-8",
    )
    g = load_ontology(tmp_project, include_l3=True, strict=True)
    # Persona must appear in the merged graph
    rows = list(g.query(
        "PREFIX myproj: <https://x.io/myproj#>\n"
        "PREFIX owl: <http://www.w3.org/2002/07/owl#>\n"
        "SELECT ?c WHERE { ?c a owl:Class . FILTER (?c = myproj:Persona) }",
    ))
    assert len(rows) == 1, "Persona class must appear exactly once in the merged graph"
    assert "myproj#Persona" in str(rows[0][0]), f"unexpected IRI: {rows[0][0]}"


def test_load_shapes_combines_three_files(builtin_shapes: Graph) -> None:
    # Sanity: combined shape graph has more triples than any single file
    assert len(builtin_shapes) > 0
    # Spot-check a representative shape from each file is present
    sh_str = builtin_shapes.serialize(format="turtle")
    assert "HasIdUniquenessShape" in sh_str  # kernel
    assert "StateEnumShape" in sh_str        # process
    assert "FeatureShape" in sh_str          # artifact
