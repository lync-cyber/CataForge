"""Limited-profile reasoning behaviour: the three axiom families must
fire, and nothing outside the profile (e.g. someValuesFrom) should."""

from __future__ import annotations

from rdflib import OWL, RDF, Graph, URIRef

from cataforge.kg.reasoning import infer

CFK = "https://cataforge.dev/ontology/kernel#"
CFA = "https://cataforge.dev/ontology/artifact#"


def _u(prefix: str, local: str) -> URIRef:
    return URIRef(prefix + local)


def test_subclass_instance_propagation_to_family(
    builtin_ontology: Graph,
) -> None:
    data = Graph()
    data.add((_u(CFA, "prd/F-001"), RDF.type, _u(CFA, "Feature")))
    derived = infer(data, builtin_ontology)
    assert (_u(CFA, "prd/F-001"), RDF.type, _u(CFA, "Need")) in derived


def test_subclass_multi_hop_to_resource(builtin_ontology: Graph) -> None:
    data = Graph()
    data.add((_u(CFA, "arch/M-001"), RDF.type, _u(CFA, "Module")))
    derived = infer(data, builtin_ontology)
    # Module ⊑ Design ⊑ Resource
    assert (_u(CFA, "arch/M-001"), RDF.type, _u(CFK, "Resource")) in derived


def test_inverse_relation_materialised(builtin_ontology: Graph) -> None:
    data = Graph()
    data.add((
        _u(CFA, "src/CU-1"),
        _u(CFA, "implements"),
        _u(CFA, "arch/M-1"),
    ))
    derived = infer(data, builtin_ontology)
    assert (
        _u(CFA, "arch/M-1"),
        _u(CFA, "implementedBy"),
        _u(CFA, "src/CU-1"),
    ) in derived


def test_inverse_reverse_direction(builtin_ontology: Graph) -> None:
    # Given only the implementedBy edge, implements must come back.
    data = Graph()
    data.add((
        _u(CFA, "arch/M-1"),
        _u(CFA, "implementedBy"),
        _u(CFA, "src/CU-1"),
    ))
    derived = infer(data, builtin_ontology)
    assert (
        _u(CFA, "src/CU-1"),
        _u(CFA, "implements"),
        _u(CFA, "arch/M-1"),
    ) in derived


def test_transitive_partof_closure(builtin_ontology: Graph) -> None:
    data = Graph()
    data.add((_u(CFA, "x"), _u(CFA, "partOf"), _u(CFA, "y")))
    data.add((_u(CFA, "y"), _u(CFA, "partOf"), _u(CFA, "z")))
    derived = infer(data, builtin_ontology)
    assert (_u(CFA, "x"), _u(CFA, "partOf"), _u(CFA, "z")) in derived


def test_transitive_long_chain(builtin_ontology: Graph) -> None:
    data = Graph()
    chain = ["a", "b", "c", "d", "e"]
    for prev, nxt in zip(chain, chain[1:], strict=False):
        data.add((_u(CFA, prev), _u(CFA, "dependsOn"), _u(CFA, nxt)))
    derived = infer(data, builtin_ontology)
    # a dependsOn e (4-hop closure)
    assert (
        _u(CFA, "a"), _u(CFA, "dependsOn"), _u(CFA, "e"),
    ) in derived


def test_derived_does_not_include_base_or_ontology(
    builtin_ontology: Graph,
) -> None:
    from rdflib import RDFS

    data = Graph()
    data.add((_u(CFA, "F-001"), RDF.type, _u(CFA, "Feature")))
    derived = infer(data, builtin_ontology)
    # Original instance assertion is in base, must not echo in derived.
    assert (_u(CFA, "F-001"), RDF.type, _u(CFA, "Feature")) not in derived
    # Ontology axiom (Feature subClassOf Need) is in ontology, also excluded.
    assert (
        _u(CFA, "Feature"), RDFS.subClassOf, _u(CFA, "Need"),
    ) not in derived


def test_empty_input_with_empty_ontology_derives_nothing() -> None:
    # When both base and ontology are empty, no rules can fire — used
    # as a sanity check that infer() returns derived-only (not base + ontology).
    derived = infer(Graph(), Graph())
    assert len(derived) == 0


def test_fixedpoint_terminates_on_acyclic_input(
    builtin_ontology: Graph,
) -> None:
    # Build a 30-node chain — must complete without hitting the safety cap
    data = Graph()
    for i in range(30):
        data.add((
            _u(CFA, f"n{i}"),
            _u(CFA, "dependsOn"),
            _u(CFA, f"n{i + 1}"),
        ))
    derived = infer(data, builtin_ontology)
    # n0 dependsOn n30
    assert (
        _u(CFA, "n0"), _u(CFA, "dependsOn"), _u(CFA, "n30"),
    ) in derived


def test_transitive_property_axiom_present(builtin_ontology: Graph) -> None:
    # Pre-condition for the transitive rule: cfa:partOf must be marked
    assert (
        _u(CFA, "partOf"), RDF.type, OWL.TransitiveProperty,
    ) in builtin_ontology
