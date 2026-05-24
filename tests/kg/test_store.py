"""Unit tests for :mod:`cataforge.kg.store`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.kg.store import (
    INSTANCES_FILENAME,
    META_FILENAME,
    SCHEMA_VERSION,
    RDFLibStore,
    StoreError,
    Triple,
    graph_dir_for,
)


def test_load_missing_file_yields_empty_store(empty_store: RDFLibStore) -> None:
    assert len(empty_store) == 0


def test_add_then_roundtrip(empty_store: RDFLibStore, tmp_project: Path) -> None:
    empty_store.add([
        Triple("cfa:prd/F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd/F-001", "rdfs:label", "login"),
    ])
    empty_store.persist()
    fresh = RDFLibStore()
    fresh.load(tmp_project)
    assert len(fresh) == 2


def test_persist_writes_sorted_nquads(empty_store: RDFLibStore, tmp_project: Path) -> None:
    # Triples added in non-alphabetical subject order; persist must reorder globally.
    empty_store.add([
        Triple("cfa:F-002", "rdf:type", "cfa:Feature"),
        Triple("cfa:F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:F-003", "rdf:type", "cfa:Feature"),
    ])
    empty_store.persist()
    nq = (graph_dir_for(tmp_project) / INSTANCES_FILENAME).read_text(
        encoding="utf-8",
    )
    lines = [ln for ln in nq.splitlines() if ln]
    assert lines == sorted(lines), "instances.nq must be lexicographically sorted"


def test_persist_sorted_nquads_global_order(tmp_path: Path) -> None:
    # Subjects with late-alphabet prefix (Z-*) added before early-alphabet (A-*).
    # Global lexicographic order must be preserved across the entire file.
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([
        Triple("cfa:Z-doc", "rdf:type", "cfa:Feature"),
        Triple("cfa:A-doc", "rdf:type", "cfa:Feature"),
    ])
    store.persist()
    nq = (graph_dir_for(tmp_path) / INSTANCES_FILENAME).read_text(encoding="utf-8")
    lines = [ln for ln in nq.splitlines() if ln]
    assert lines == sorted(lines), (
        "instances.nq sort must be globally lexicographic, not insertion-order"
    )
    # A-doc line must come before Z-doc line
    a_idx = next(i for i, ln in enumerate(lines) if "A-doc" in ln)
    z_idx = next(i for i, ln in enumerate(lines) if "Z-doc" in ln)
    assert a_idx < z_idx, "A-doc must sort before Z-doc"


def test_persist_writes_meta_json(empty_store: RDFLibStore, tmp_project: Path) -> None:
    empty_store.add([Triple("cfa:F-001", "rdf:type", "cfa:Feature")])
    empty_store.persist()
    meta = json.loads(
        (graph_dir_for(tmp_project) / META_FILENAME).read_text(encoding="utf-8"),
    )
    assert meta["schema_version"] == SCHEMA_VERSION
    assert meta["store_backend"] == "rdflib"
    assert meta["triple_count"] == 1
    assert "generated_at" in meta


def test_persist_without_load_raises() -> None:
    store = RDFLibStore()
    with pytest.raises(StoreError):
        store.persist()


def test_named_graph_isolation(empty_store: RDFLibStore, tmp_project: Path) -> None:
    empty_store.add(
        [Triple("cfa:X", "rdf:type", "cfa:Feature")],
        named_graph="cfp:invocation/inv-1",
    )
    empty_store.add([Triple("cfa:Y", "rdf:type", "cfa:Feature")])
    empty_store.persist()
    fresh = RDFLibStore()
    fresh.load(tmp_project)
    contexts = {row[3] for row in fresh}
    assert None in contexts, "default graph quad missing"
    assert any(g and "inv-1" in g for g in contexts), "named graph quad missing"


def test_remove_with_wildcard(empty_store: RDFLibStore) -> None:
    empty_store.add([
        Triple("cfa:F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:F-001", "rdfs:label", "login"),
        Triple("cfa:F-002", "rdf:type", "cfa:Feature"),
    ])
    removed = empty_store.remove(Triple("cfa:F-001", "*", "*"))
    assert removed == 2
    assert len(empty_store) == 1


def test_literal_int_coerced(empty_store: RDFLibStore, tmp_project: Path) -> None:
    empty_store.add([Triple("cfa:F-001", "cfa:priority", 1)])
    empty_store.persist()
    nq = (graph_dir_for(tmp_project) / INSTANCES_FILENAME).read_text(
        encoding="utf-8",
    )
    assert "XMLSchema#integer" in nq, "integer literal must carry xsd:integer datatype"


def test_literal_bool_not_treated_as_int(empty_store: RDFLibStore) -> None:
    empty_store.add([Triple("cfa:F-001", "cfa:flag", True)])
    rows = empty_store.query(
        "PREFIX cfa: <https://cataforge.dev/ontology/artifact#>\n"
        "SELECT ?o WHERE { <https://cataforge.dev/ontology/artifact#F-001> "
        "cfa:flag ?o }",
    )
    assert rows[0]["o"] == "true"


def test_query_select_returns_rows(empty_store: RDFLibStore) -> None:
    empty_store.add([
        Triple("cfa:F-001", "rdfs:label", "login"),
        Triple("cfa:F-002", "rdfs:label", "signup"),
    ])
    rows = empty_store.query(
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        "SELECT ?l WHERE { ?x rdfs:label ?l } ORDER BY ?l",
    )
    assert [r["l"] for r in rows] == ["login", "signup"]


def test_query_ask(empty_store: RDFLibStore) -> None:
    empty_store.add([Triple("cfa:F-001", "rdf:type", "cfa:Feature")])
    rows = empty_store.query(
        "PREFIX cfa: <https://cataforge.dev/ontology/artifact#>\n"
        "ASK { ?x a cfa:Feature }",
    )
    assert rows == [{"_ask": "true"}]


def test_curie_unknown_prefix_raises(empty_store: RDFLibStore) -> None:
    with pytest.raises(StoreError):
        empty_store.add([Triple("zz:F-001", "rdf:type", "cfa:Feature")])


def test_update_inserts_triple(empty_store: RDFLibStore) -> None:
    empty_store.update(
        "PREFIX cfa: <https://cataforge.dev/ontology/artifact#>\n"
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        "INSERT DATA { cfa:F-001 rdfs:label 'inserted' }",
    )
    assert len(empty_store) == 1
