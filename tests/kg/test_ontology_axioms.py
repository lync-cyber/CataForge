"""Axiom-level checks against the bundled L0/L1/L2 ontology graphs.

These tests assert structural invariants the design note §1 promises so
later edits to ``data/*.ttl`` cannot silently regress them."""

from __future__ import annotations

import pytest
from rdflib import OWL, RDF, RDFS, Graph, URIRef

CFK = "https://cataforge.dev/ontology/kernel#"
CFP = "https://cataforge.dev/ontology/process#"
CFA = "https://cataforge.dev/ontology/artifact#"


def _u(prefix: str, local: str) -> URIRef:
    return URIRef(prefix + local)


@pytest.mark.parametrize("local", [
    "Resource", "Document", "Section", "Identifier", "Standard",
])
def test_kernel_classes_present(builtin_ontology: Graph, local: str) -> None:
    assert (_u(CFK, local), RDF.type, OWL.Class) in builtin_ontology


@pytest.mark.parametrize("local", [
    "Agent", "Skill", "Phase", "Invocation", "Event", "Hook",
])
def test_process_classes_present(builtin_ontology: Graph, local: str) -> None:
    assert (_u(CFP, local), RDF.type, OWL.Class) in builtin_ontology


@pytest.mark.parametrize("local", [
    "Need", "Design", "Implementation", "Verification",
    "Governance", "Operation",
])
def test_artifact_families_present(builtin_ontology: Graph, local: str) -> None:
    assert (_u(CFA, local), RDF.type, OWL.Class) in builtin_ontology


@pytest.mark.parametrize("concrete,family", [
    ("Feature", "Need"),
    ("UserStory", "Need"),
    ("NFR", "Need"),
    ("Module", "Design"),
    ("Component", "Design"),
    ("Interface", "Design"),
    ("Workflow", "Design"),
    ("CodeUnit", "Implementation"),
    ("TestCase", "Verification"),
    ("TestSuite", "Verification"),
    ("AcceptanceCriterion", "Verification"),
    ("Task", "Governance"),
    ("Decision", "Governance"),
    ("Risk", "Governance"),
    ("Release", "Operation"),
    ("Incident", "Operation"),
])
def test_concrete_classes_under_family(
    builtin_ontology: Graph, concrete: str, family: str,
) -> None:
    assert (
        _u(CFA, concrete), RDFS.subClassOf, _u(CFA, family),
    ) in builtin_ontology


def test_v_model_families_disjoint(builtin_ontology: Graph) -> None:
    pairs = [
        ("Need", "Design"),
        ("Need", "Implementation"),
        ("Need", "Verification"),
        ("Design", "Implementation"),
        ("Design", "Verification"),
        ("Implementation", "Verification"),
    ]
    for a, b in pairs:
        assert (_u(CFA, a), OWL.disjointWith, _u(CFA, b)) in builtin_ontology


@pytest.mark.parametrize("prop,domain,range_", [
    ("realizes",   "Design",         "Need"),
    ("implements", "Implementation", "Design"),
    ("validates",  "Verification",   None),  # range is cfk:Resource
])
def test_v_model_relations_typed(
    builtin_ontology: Graph, prop: str, domain: str, range_: str | None,
) -> None:
    p = _u(CFA, prop)
    assert (p, RDFS.domain, _u(CFA, domain)) in builtin_ontology
    if range_ is not None:
        assert (p, RDFS.range, _u(CFA, range_)) in builtin_ontology


def test_transitive_properties_marked(builtin_ontology: Graph) -> None:
    for local in ("traces", "partOf", "dependsOn"):
        assert (
            _u(CFA, local), RDF.type, OWL.TransitiveProperty,
        ) in builtin_ontology


def test_inverse_pairs_declared(builtin_ontology: Graph) -> None:
    pairs = [
        ("realizedBy", "realizes"),
        ("implementedBy", "implements"),
        ("decomposedBy", "decomposes"),
        ("validatedBy", "validates"),
        ("renderedBy", "renders"),
    ]
    for inv, fwd in pairs:
        assert (
            _u(CFA, inv), OWL.inverseOf, _u(CFA, fwd),
        ) in builtin_ontology


def test_kernel_functional_properties(builtin_ontology: Graph) -> None:
    for local in ("hasId", "createdAt", "modifiedAt"):
        assert (
            _u(CFK, local), RDF.type, OWL.FunctionalProperty,
        ) in builtin_ontology
