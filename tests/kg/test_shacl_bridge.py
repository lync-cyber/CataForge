"""Tests for the SHACL runtime bridge (P2 task W2).

Verifies pyoxigraph → rdflib conversion and SHACL validation when
both pyshacl and rdflib are available.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_HAS_SHACL_DEPS = (
    importlib.util.find_spec("pyshacl") is not None
    and importlib.util.find_spec("rdflib") is not None
)


def _make_store_with_entity():
    """Create a memory store with one well-formed Feature entity."""
    import pyoxigraph as ox

    store = ox.Store()
    ns = "https://cataforge.dev/ontology/"
    inst = "https://cataforge.dev/instance/"
    triples = [
        (ox.NamedNode(f"{inst}F-001"), ox.NamedNode(f"{ns}entity_id"), ox.Literal("F-001")),
        (ox.NamedNode(f"{inst}F-001"), ox.NamedNode(f"{ns}title"), ox.Literal("Login")),
        (ox.NamedNode(f"{inst}F-001"), ox.NamedNode(f"{ns}sort_key"), ox.Literal("F:001")),
        (
            ox.NamedNode(f"{inst}F-001"),
            ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
            ox.NamedNode(f"{ns}Feature"),
        ),
    ]
    for s, p, o in triples:
        store.add(ox.Quad(s, p, o, ox.DefaultGraph()))
    return store


def test_pyoxigraph_to_rdflib_roundtrip() -> None:
    if not _HAS_SHACL_DEPS:
        pytest.skip("rdflib not installed")

    from cataforge.domain.kg.validate import _pyoxigraph_to_rdflib

    store = _make_store_with_entity()
    g = _pyoxigraph_to_rdflib(store)

    assert len(g) == 4, f"expected 4 triples, got {len(g)}"

    import rdflib

    ns = rdflib.Namespace("https://cataforge.dev/ontology/")
    inst = rdflib.Namespace("https://cataforge.dev/instance/")

    assert (inst["F-001"], ns.entity_id, rdflib.Literal("F-001")) in g
    assert (inst["F-001"], rdflib.RDF.type, ns.Feature) in g


def test_ox_to_rdflib_handles_datatypes() -> None:
    if not _HAS_SHACL_DEPS:
        pytest.skip("rdflib not installed")

    import pyoxigraph as ox
    import rdflib

    from cataforge.domain.kg.validate import _ox_to_rdflib_term

    named = ox.NamedNode("http://example.org/x")
    assert _ox_to_rdflib_term(named) == rdflib.URIRef("http://example.org/x")

    blank = ox.BlankNode("b0")
    result = _ox_to_rdflib_term(blank)
    assert isinstance(result, rdflib.BNode)

    lit_plain = ox.Literal("hello")
    assert _ox_to_rdflib_term(lit_plain) == rdflib.Literal("hello")

    lit_lang = ox.Literal("hola", language="es")
    assert _ox_to_rdflib_term(lit_lang) == rdflib.Literal("hola", lang="es")

    xsd_int = ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer")
    lit_typed = ox.Literal("42", datatype=xsd_int)
    result = _ox_to_rdflib_term(lit_typed)
    assert result.datatype == rdflib.URIRef("http://www.w3.org/2001/XMLSchema#integer")


def test_run_shacl_skips_when_deps_missing() -> None:
    from cataforge.domain.kg.validate import _run_shacl

    store = _make_store_with_entity()
    skipped, violations = _run_shacl(store)
    if not _HAS_SHACL_DEPS:
        assert skipped is True
        assert violations == []


def test_run_shacl_skips_when_shapes_file_missing() -> None:
    if not _HAS_SHACL_DEPS:
        pytest.skip("rdflib/pyshacl not installed")

    from unittest.mock import patch

    from cataforge.domain.kg.validate import _run_shacl

    store = _make_store_with_entity()
    with patch("cataforge.domain.kg.validate._find_shapes_file", return_value=None):
        skipped, violations = _run_shacl(store)

    assert skipped is True
    assert violations == []


def test_run_shacl_detects_violation_with_inline_shapes(
    tmp_path: Path,
) -> None:
    if not _HAS_SHACL_DEPS:
        pytest.skip("rdflib/pyshacl not installed")

    from unittest.mock import patch

    from cataforge.domain.kg.validate import _run_shacl

    shapes_ttl = tmp_path / "shapes.ttl"
    shapes_ttl.write_text(
        """\
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix cf: <https://cataforge.dev/ontology/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

cf:FeatureShape a sh:NodeShape ;
    sh:targetClass cf:Feature ;
    sh:property [
        sh:path cf:description ;
        sh:minCount 1 ;
        sh:message "Feature must have a description" ;
    ] .
""",
        encoding="utf-8",
    )

    store = _make_store_with_entity()
    with patch("cataforge.domain.kg.validate._find_shapes_file", return_value=shapes_ttl):
        skipped, violations = _run_shacl(store)

    assert skipped is False
    assert len(violations) >= 1, f"expected SHACL violation, got {violations}"
    assert any("description" in v.message.lower() for v in violations)


def test_run_shacl_passes_with_conforming_data(
    tmp_path: Path,
) -> None:
    if not _HAS_SHACL_DEPS:
        pytest.skip("rdflib/pyshacl not installed")

    from unittest.mock import patch

    from cataforge.domain.kg.validate import _run_shacl

    shapes_ttl = tmp_path / "shapes.ttl"
    shapes_ttl.write_text(
        """\
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix cf: <https://cataforge.dev/ontology/> .

cf:FeatureShape a sh:NodeShape ;
    sh:targetClass cf:Feature ;
    sh:property [
        sh:path cf:entity_id ;
        sh:minCount 1 ;
    ] ;
    sh:property [
        sh:path cf:title ;
        sh:minCount 1 ;
    ] .
""",
        encoding="utf-8",
    )

    store = _make_store_with_entity()
    with patch("cataforge.domain.kg.validate._find_shapes_file", return_value=shapes_ttl):
        skipped, violations = _run_shacl(store)

    assert skipped is False
    assert violations == [], f"unexpected violations: {violations}"
