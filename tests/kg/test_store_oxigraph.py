"""Oxigraph backend conformance — skipped when pyoxigraph isn't installed.

Mirrors a slice of :mod:`tests/kg/test_store.py` so the two backends
are guaranteed to behave the same on the API surface ``RDFLibStore``
already exercises. If/when pyoxigraph is pinned as a hard dependency
the skip marker can be dropped."""

from __future__ import annotations

from pathlib import Path

import pytest

pyoxigraph = pytest.importorskip(
    "pyoxigraph",
    reason="cataforge[oxigraph] extra not installed",
)

from cataforge.kg.store import Triple  # noqa: E402
from cataforge.kg.store_oxigraph import OxigraphStore  # noqa: E402


def _project(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    return tmp_path


# ---------- crud parity ----------

def test_add_then_query_round_trip(tmp_path: Path) -> None:
    store = OxigraphStore()
    store.load(_project(tmp_path))
    store.add([
        Triple("cfa:m/M1", "rdf:type", "cfa:Module"),
        Triple("cfa:m/M1", "cfk:hasId", "M-001"),
    ])
    rows = store.query("SELECT ?id WHERE { ?m cfk:hasId ?id } ORDER BY ?id")
    assert any("M-001" in r["id"] for r in rows)


def test_remove_pattern_returns_delta(tmp_path: Path) -> None:
    store = OxigraphStore()
    store.load(_project(tmp_path))
    store.add([
        Triple("cfa:m/A", "rdf:type", "cfa:Module"),
        Triple("cfa:m/B", "rdf:type", "cfa:Module"),
    ])
    n = store.remove(Triple("cfa:m/A", "rdf:type", "cfa:Module"))
    assert n == 1


def test_ask_returns_uniform_dict(tmp_path: Path) -> None:
    store = OxigraphStore()
    store.load(_project(tmp_path))
    store.add([Triple("cfa:f/F1", "rdf:type", "cfa:Feature")])
    rows = store.query("ASK { ?f a cfa:Feature }")
    assert rows == [{"_ask": "true"}]


def test_persist_writes_snapshot(tmp_path: Path) -> None:
    project = _project(tmp_path)
    store = OxigraphStore()
    store.load(project)
    store.add([Triple("cfa:m/M1", "rdf:type", "cfa:Module")])
    store.persist()
    snapshot = project / "docs" / ".doc-graph" / "oxigraph"
    assert snapshot.is_dir()
    assert any(snapshot.iterdir())


def test_iter_classifies_named_node_and_literal(tmp_path: Path) -> None:
    store = OxigraphStore()
    store.load(_project(tmp_path))
    store.add([
        Triple("cfa:m/M1", "rdf:type", "cfa:Module"),
        Triple("cfa:m/M1", "cfk:hasId", "M-001"),
    ])
    triples = list(store)
    obj_values = {o for _, _, o, _ in triples}
    # NamedNode object (cfa:Module IRI) must appear as bare IRI, not '<...>'
    assert any(v.startswith("https://") for v in obj_values), (
        "NamedNode object must serialize to a bare IRI string"
    )
    # Literal object must appear as its lexical value, not as '"M-001"'
    assert "M-001" in obj_values, (
        "Literal object must serialize to its lexical value"
    )
    assert '"M-001"' not in obj_values, (
        "Literal object must not include rdflib-style quotes"
    )
