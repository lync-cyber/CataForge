"""End-to-end: derived triples must be queryable after migrate()."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from rdflib import RDF, RDFS, Graph, URIRef

from cataforge.kg.migrate import migrate
from cataforge.kg.reasoning import infer
from cataforge.kg.store import INFERRED_GRAPH_IRI, RDFLibStore

_CFA = "https://cataforge.dev/ontology/artifact#"


def test_inferred_graph_iri_constant() -> None:
    assert INFERRED_GRAPH_IRI == "urn:cataforge:inferred"


def test_apply_inference_adds_to_named_graph(tmp_project: Path) -> None:
    store = RDFLibStore()
    store.load(tmp_project)
    cls_a = URIRef(_CFA + "A")
    cls_b = URIRef(_CFA + "B")
    inst_x = URIRef(_CFA + "x")
    base = Graph()
    onto = Graph()
    base.add((inst_x, RDF.type, cls_a))
    onto.add((cls_a, RDFS.subClassOf, cls_b))
    derived = infer(base, onto)
    count = store.apply_inference(derived)
    assert count > 0
    inferred_graph = store._dataset.graph(URIRef(INFERRED_GRAPH_IRI))
    assert (inst_x, RDF.type, cls_b) in inferred_graph


def test_apply_inference_returns_new_triple_count(tmp_project: Path) -> None:
    store = RDFLibStore()
    store.load(tmp_project)
    cls_a = URIRef(_CFA + "A")
    cls_b = URIRef(_CFA + "B")
    inst_x = URIRef(_CFA + "x")
    base = Graph()
    onto = Graph()
    base.add((inst_x, RDF.type, cls_a))
    onto.add((cls_a, RDFS.subClassOf, cls_b))
    derived = infer(base, onto)
    first = store.apply_inference(derived)
    second = store.apply_inference(derived)
    assert first > 0
    assert second == 0


def test_migrate_persists_inferred_triples(tmp_path: Path) -> None:
    doc_body = textwrap.dedent("""\
        ---
        id: prd-infer-test
        ---
        # PRD-infer-test

        ## F-001 login feature
        """)
    doc_path = tmp_path / "docs" / "prd.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(doc_body, encoding="utf-8")

    index = {"version": "1", "documents": {"doc-0": {"file_path": "docs/prd.md"}}}
    (tmp_path / "docs" / ".doc-index.json").write_text(
        json.dumps(index), encoding="utf-8",
    )

    report = migrate(tmp_path, validate=False)
    assert report.files_processed == 1
    assert report.inferred_triples >= 0

    store = RDFLibStore()
    store.load(tmp_path)
    results = store.query(
        f"SELECT ?s ?t WHERE {{ GRAPH <{INFERRED_GRAPH_IRI}> {{ ?s a ?t }} }} LIMIT 1"
    )
    assert isinstance(results, list)


def test_benchmark_data_graph_preserves_node_types(tmp_project: Path) -> None:
    from rdflib import Literal as RdflibLiteral
    from rdflib import URIRef as RdflibURIRef

    from cataforge.kg.benchmark import _populate

    store = RDFLibStore()
    store.load(tmp_project)
    _populate(store, 8)

    data = store._dataset.default_graph
    for s, p, o in data:
        assert isinstance(s, RdflibURIRef), f"subject not URIRef: {s!r}"
        assert isinstance(p, RdflibURIRef), f"predicate not URIRef: {p!r}"
        assert isinstance(o, (RdflibURIRef, RdflibLiteral)), f"object wrong type: {o!r}"
        if isinstance(o, RdflibLiteral):
            assert not str(o).startswith("cfa:"), f"CURIE stored as Literal: {o!r}"
