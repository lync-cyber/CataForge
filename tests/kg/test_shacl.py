"""SHACL constraint behaviour — bundled shapes must catch the violations
they advertise without false-positives on conformant data."""

from __future__ import annotations

from pyshacl import validate as pyshacl_validate
from rdflib import RDF, RDFS, Graph, Literal, URIRef
from rdflib.namespace import SH

CFK = "https://cataforge.dev/ontology/kernel#"
CFA = "https://cataforge.dev/ontology/artifact#"
CFP = "https://cataforge.dev/ontology/process#"


def _u(prefix: str, local: str) -> URIRef:
    return URIRef(prefix + local)


def _conforming_feature_graph() -> Graph:
    """A minimal data graph that satisfies every Feature-related shape."""
    g = Graph()
    g.add((_u(CFK, "doc/prd-x"), RDF.type, _u(CFK, "Document")))
    g.add((_u(CFK, "doc/prd-x"), RDFS.label, Literal("PRD-X")))
    g.add((_u(CFA, "prd-x/F-001"), RDF.type, _u(CFA, "Feature")))
    g.add((_u(CFA, "prd-x/F-001"), _u(CFK, "hasId"), Literal("F-001")))
    g.add((_u(CFA, "prd-x/F-001"), RDFS.label, Literal("login")))
    g.add((_u(CFA, "prd-x/F-001"), _u(CFK, "definedIn"), _u(CFK, "doc/prd-x")))
    return g


def _validate(data: Graph, shapes: Graph, ontology: Graph) -> tuple[bool, Graph]:
    conforms, results_graph, _ = pyshacl_validate(
        data_graph=data,
        shacl_graph=shapes,
        ont_graph=ontology,
        inference="rdfs",
        advanced=True,
        debug=False,
    )
    return bool(conforms), results_graph


def _violation_count(results_graph: Graph) -> int:
    return sum(
        1
        for _ in results_graph.subjects(
            predicate=SH.resultSeverity, object=SH.Violation,
        )
    )


def test_conforming_feature_passes(
    builtin_shapes: Graph, builtin_ontology: Graph,
) -> None:
    conforms, _ = _validate(
        _conforming_feature_graph(), builtin_shapes, builtin_ontology,
    )
    assert conforms


def test_feature_id_pattern_violation(
    builtin_shapes: Graph, builtin_ontology: Graph,
) -> None:
    data = _conforming_feature_graph()
    data.remove((_u(CFA, "prd-x/F-001"), _u(CFK, "hasId"), Literal("F-001")))
    data.add((_u(CFA, "prd-x/F-001"), _u(CFK, "hasId"), Literal("X-bad")))
    conforms, _ = _validate(data, builtin_shapes, builtin_ontology)
    assert not conforms


def test_feature_missing_label_violation(
    builtin_shapes: Graph, builtin_ontology: Graph,
) -> None:
    data = _conforming_feature_graph()
    data.remove((_u(CFA, "prd-x/F-001"), RDFS.label, Literal("login")))
    conforms, _ = _validate(data, builtin_shapes, builtin_ontology)
    assert not conforms


def test_status_enum_violation(
    builtin_shapes: Graph, builtin_ontology: Graph,
) -> None:
    data = _conforming_feature_graph()
    data.add((_u(CFA, "prd-x/F-001"), _u(CFA, "status"), Literal("bogus")))
    conforms, _ = _validate(data, builtin_shapes, builtin_ontology)
    assert not conforms


def test_status_enum_allowed_value_passes(
    builtin_shapes: Graph, builtin_ontology: Graph,
) -> None:
    data = _conforming_feature_graph()
    data.add((_u(CFA, "prd-x/F-001"), _u(CFA, "status"), Literal("active")))
    conforms, _ = _validate(data, builtin_shapes, builtin_ontology)
    assert conforms


def test_state_enum_violation(
    builtin_shapes: Graph, builtin_ontology: Graph,
) -> None:
    data = _conforming_feature_graph()
    inv = _u(CFP, "invocation/inv-1")
    data.add((inv, RDF.type, _u(CFP, "Invocation")))
    data.add((inv, _u(CFP, "state"), Literal("unknown")))
    conforms, _ = _validate(data, builtin_shapes, builtin_ontology)
    assert not conforms


def test_v_model_disjoint_violation(
    builtin_shapes: Graph, builtin_ontology: Graph,
) -> None:
    data = _conforming_feature_graph()
    # Add a node that is both Need (via Feature) and Design (via Module)
    mix = _u(CFA, "mix/X-1")
    data.add((mix, RDF.type, _u(CFA, "Feature")))
    data.add((mix, RDF.type, _u(CFA, "Module")))
    data.add((mix, _u(CFK, "hasId"), Literal("F-099")))
    data.add((mix, RDFS.label, Literal("mixed")))
    data.add((mix, _u(CFK, "definedIn"), _u(CFK, "doc/prd-x")))
    conforms, results = _validate(data, builtin_shapes, builtin_ontology)
    assert not conforms
    # NeedDisjointShape (or one of the V-model disjoint shapes) must fire
    text = results.serialize(format="turtle")
    assert "DisjointShape" in text or "NotConstraintComponent" in text


def test_release_id_must_be_semver(
    builtin_shapes: Graph, builtin_ontology: Graph,
) -> None:
    data = Graph()
    rel = _u(CFA, "release/abc")
    data.add((rel, RDF.type, _u(CFA, "Release")))
    data.add((rel, _u(CFK, "hasId"), Literal("not-semver")))
    conforms, _ = _validate(data, builtin_shapes, builtin_ontology)
    assert not conforms

    data2 = Graph()
    rel2 = _u(CFA, "release/v050")
    data2.add((rel2, RDF.type, _u(CFA, "Release")))
    data2.add((rel2, _u(CFK, "hasId"), Literal("v0.5.0")))
    conforms2, _ = _validate(data2, builtin_shapes, builtin_ontology)
    assert conforms2


def test_code_unit_kind_enum(
    builtin_shapes: Graph, builtin_ontology: Graph,
) -> None:
    data = Graph()
    cu = _u(CFA, "src/CU-1")
    data.add((cu, RDF.type, _u(CFA, "CodeUnit")))
    data.add((cu, _u(CFK, "hasId"), Literal("CU-001")))
    data.add((cu, _u(CFA, "codeUnitKind"), Literal("invalid-kind")))
    conforms, _ = _validate(data, builtin_shapes, builtin_ontology)
    assert not conforms


def test_invocation_started_before_completed(
    builtin_shapes: Graph, builtin_ontology: Graph,
) -> None:
    from rdflib import XSD

    data = Graph()
    inv = _u(CFP, "invocation/inv-bad")
    data.add((inv, RDF.type, _u(CFP, "Invocation")))
    data.add((
        inv, _u(CFP, "startedAt"),
        Literal("2026-05-24T12:00:00Z", datatype=XSD.dateTime),
    ))
    data.add((
        inv, _u(CFP, "completedAt"),
        Literal("2026-05-24T11:00:00Z", datatype=XSD.dateTime),
    ))
    conforms, _ = _validate(data, builtin_shapes, builtin_ontology)
    assert not conforms
