"""§6.4 A13 — KG bidirectional coverage assassinates the regex false positive.

Mirrors the Task 6 §6.6.4 skeleton 1: a Feature mentioned in
narrative prose without an asserted `cf:implements` edge MUST NOT be
counted as covered under `strict` coverage mode. The legacy regex
pass (`re.search(F-001, arch_body)`) returns True for any string
mention; the KG SPARQL pass requires an actual edge.
"""

from __future__ import annotations


def _empty_memory_kg():
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    kg = KnowledgeGraph(handle.raw, config)
    return kg, handle


def _add_quad(store, *, subject: str, predicate: str, obj):
    import pyoxigraph as ox

    s = ox.NamedNode(subject)
    p = ox.NamedNode(predicate)
    o = ox.NamedNode(obj) if isinstance(obj, str) and obj.startswith("http") else ox.Literal(obj)
    store.add(ox.Quad(s, p, o))


_CF = "https://cataforge.dev/ontology/"
_INST = "https://cataforge.dev/instance/"
_RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def _add_feature(store, entity_id: str, title: str, sort_key: str | None = None) -> str:
    iri = f"{_INST}{entity_id}"
    sk = sort_key or f"F:{int(entity_id.split('-')[1]):06d}"
    _add_quad(store, subject=iri, predicate=_RDF_TYPE, obj=f"{_CF}Feature")
    _add_quad(store, subject=iri, predicate=f"{_CF}entity_id", obj=entity_id)
    _add_quad(store, subject=iri, predicate=f"{_CF}sort_key", obj=sk)
    _add_quad(store, subject=iri, predicate=f"{_CF}title", obj=title)
    return iri


def _add_module(store, entity_id: str, title: str, implements_iri: str | None = None) -> str:
    iri = f"{_INST}{entity_id}"
    sk = f"M:{int(entity_id.split('-')[1]):06d}"
    _add_quad(store, subject=iri, predicate=_RDF_TYPE, obj=f"{_CF}Module")
    _add_quad(store, subject=iri, predicate=f"{_CF}entity_id", obj=entity_id)
    _add_quad(store, subject=iri, predicate=f"{_CF}sort_key", obj=sk)
    _add_quad(store, subject=iri, predicate=f"{_CF}title", obj=title)
    if implements_iri:
        _add_quad(store, subject=iri, predicate=f"{_CF}implements", obj=implements_iri)
    return iri


def test_kg_coverage_rejects_regex_false_positive() -> None:
    """A Feature appears in narrative ("see F-001 for background")
    but no Module asserts `cf:implements F-001`. The legacy regex
    would return True; the KG check returns has_impl=False.
    """
    kg, _ = _empty_memory_kg()
    # Setup: Feature exists, no implementing Module.
    _add_feature(kg.store, "F-001", "Login flow")

    cov = kg.trace.coverage("F-001")
    assert cov["has_impl"] is False
    assert cov["has_test"] is False
    assert cov["status"] == "none"


def test_kg_coverage_recognises_real_implementation() -> None:
    """Positive test: a Module with `cf:implements` edge counts as coverage."""
    kg, _ = _empty_memory_kg()
    f_iri = _add_feature(kg.store, "F-002", "Password reset")
    _add_module(kg.store, "M-020", "ResetService", implements_iri=f_iri)

    cov = kg.trace.coverage("F-002")
    assert cov["has_impl"] is True
    assert cov["has_test"] is False
    assert cov["status"] == "partial"


def test_bidirectional_coverage_report_segregates_features() -> None:
    """`bidirectional_coverage()` returns one row per Feature; rows
    must distinguish covered from uncovered without lumping them.
    """
    kg, _ = _empty_memory_kg()
    _add_feature(kg.store, "F-001", "uncovered feature")
    f_iri = _add_feature(kg.store, "F-002", "covered feature")
    _add_module(kg.store, "M-020", "ResetService", implements_iri=f_iri)

    rows = {r.entity_id: r for r in kg.trace.bidirectional_coverage()}
    assert rows["F-001"].has_impl is False
    assert rows["F-002"].has_impl is True
