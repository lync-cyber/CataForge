"""End-to-end smoke tests for RDFLibStore: add → query → persist → reload → query."""

from __future__ import annotations

from pathlib import Path

from cataforge.kg.store import RDFLibStore, Triple


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    return tmp_path


_SUBJECT = "https://cataforge.dev/ontology/artifact#F-smoke-999"
_SUBJECT_IRI = f"<{_SUBJECT}>"


def test_roundtrip_default_graph(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    store = RDFLibStore()
    store.load(project)
    store.add([Triple(_SUBJECT, "rdf:type", "cfa:Feature")])
    store.add([Triple(_SUBJECT, "rdfs:label", "smoke-feature")])

    rows = store.query(
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        f"SELECT ?lbl WHERE {{ {_SUBJECT_IRI} rdfs:label ?lbl }}",
    )
    assert len(rows) == 1
    assert rows[0]["lbl"] == "smoke-feature"

    store.persist()

    fresh = RDFLibStore()
    fresh.load(project)
    assert len(fresh) == 2

    rows2 = fresh.query(
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        f"SELECT ?lbl WHERE {{ {_SUBJECT_IRI} rdfs:label ?lbl }}",
    )
    assert len(rows2) == 1
    assert rows2[0]["lbl"] == "smoke-feature"


_SUBJECT_888 = "https://cataforge.dev/ontology/artifact#F-smoke-888"
_SUBJECT_777 = "https://cataforge.dev/ontology/artifact#F-smoke-777"


def test_roundtrip_named_graph(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    store = RDFLibStore()
    store.load(project)
    store.add(
        [Triple(_SUBJECT_888, "rdf:type", "cfa:Feature")],
        named_graph="cfp:invocation/inv-smoke",
    )
    store.add([Triple(_SUBJECT_777, "rdf:type", "cfa:Feature")])
    store.persist()

    fresh = RDFLibStore()
    fresh.load(project)
    assert len(fresh) == 2

    graph_names = {row[3] for row in fresh}
    assert None in graph_names
    assert any(g and "inv-smoke" in g for g in graph_names)


def test_update_inserts_into_default_graph(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    store = RDFLibStore()
    store.load(project)
    store.update(
        "PREFIX cfa: <https://cataforge.dev/ontology/artifact#>\n"
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        "INSERT DATA { cfa:F-update rdfs:label 'updated' }",
    )
    assert len(store) == 1

    rows = store.query(
        "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
        "SELECT ?lbl WHERE { ?s rdfs:label ?lbl }",
    )
    assert rows[0]["lbl"] == "updated"


def test_persist_and_reload_iri_integrity(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    subject_iri = "https://cataforge.dev/ontology/artifact#prd/F-roundtrip"
    predicate_iri = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
    object_iri = "https://cataforge.dev/ontology/artifact#Feature"

    store = RDFLibStore()
    store.load(project)
    store.add([Triple(subject_iri, predicate_iri, object_iri)])
    store.persist()

    fresh = RDFLibStore()
    fresh.load(project)
    rows = fresh.query(
        f"SELECT ?o WHERE {{ <{subject_iri}> <{predicate_iri}> ?o }}",
    )
    assert len(rows) == 1
    assert rows[0]["o"] == object_iri
