"""Limited-profile reasoning + SHACL validation helpers.

The framework deliberately does NOT run the full OWL-2-RL ruleset. Per
design note §9.2 R-06, only three axiom families are materialised:

1. ``rdfs:subClassOf`` transitivity and instance propagation
   (``A ⊑ B, B ⊑ C ⊢ A ⊑ C`` and ``x : A, A ⊑ B ⊢ x : B``).
2. ``owl:inverseOf`` symmetric materialisation in both directions.
3. ``owl:TransitiveProperty`` transitive closure.

This keeps reasoning bounded — heavy axioms like ``owl:someValuesFrom``,
``owl:disjointWith`` propagation, and equality reasoning are intentionally
left to SHACL (closed-world, faster, easier to debug).
"""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph

from cataforge.kg.ontology import bind_namespaces
from cataforge.kg.store import GraphStore, ValidationReport

# Iteration safety cap. Reasoning runs against the limited-profile rules
# below, which have polynomial fixed-point depth; 50 rounds is far above
# anything realistic and exists only to bound pathological inputs.
_MAX_FIXEDPOINT_ROUNDS = 50

_PREFIXES = (
    "PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
    "PREFIX owl:  <http://www.w3.org/2002/07/owl#>\n"
)

_RULES: tuple[str, ...] = (
    # subClassOf transitivity
    """
    INSERT { ?a rdfs:subClassOf ?c }
    WHERE  {
        ?a rdfs:subClassOf ?b .
        ?b rdfs:subClassOf ?c .
        FILTER (?a != ?c)
        FILTER NOT EXISTS { ?a rdfs:subClassOf ?c }
    }
    """,
    # instance propagation up the class hierarchy
    """
    INSERT { ?x rdf:type ?super }
    WHERE  {
        ?x rdf:type ?sub .
        ?sub rdfs:subClassOf+ ?super .
        FILTER NOT EXISTS { ?x rdf:type ?super }
    }
    """,
    # inverseOf (forward direction)
    """
    INSERT { ?o ?p2 ?s }
    WHERE  {
        ?p1 owl:inverseOf ?p2 .
        ?s ?p1 ?o .
        FILTER NOT EXISTS { ?o ?p2 ?s }
    }
    """,
    # inverseOf (reverse direction so the relation closes symmetrically)
    """
    INSERT { ?s ?p1 ?o }
    WHERE  {
        ?p1 owl:inverseOf ?p2 .
        ?o ?p2 ?s .
        FILTER NOT EXISTS { ?s ?p1 ?o }
    }
    """,
    # TransitiveProperty closure
    """
    INSERT { ?s ?p ?o }
    WHERE  {
        ?p a owl:TransitiveProperty .
        ?s ?p ?x .
        ?x ?p ?o .
        FILTER (?s != ?o)
        FILTER NOT EXISTS { ?s ?p ?o }
    }
    """,
)


def infer(base: Graph, ontology: Graph) -> Graph:
    """Compute derived triples under the limited profile.

    Returns a new Graph containing **only** the inferred triples — neither
    the original data nor the ontology axioms are echoed back. Callers
    typically persist this graph to ``docs/.doc-graph/inferred.nq`` (which
    is gitignored per design §2.2) and re-derive it on demand."""
    work = Graph()
    for stmt in base:
        work.add(stmt)
    for stmt in ontology:
        work.add(stmt)
    bind_namespaces(work)

    for _ in range(_MAX_FIXEDPOINT_ROUNDS):
        before = len(work)
        for rule_body in _RULES:
            work.update(_PREFIXES + rule_body)
        if len(work) == before:
            break

    base_set = set(base)
    onto_set = set(ontology)
    derived = Graph()
    bind_namespaces(derived)
    for stmt in work:
        if stmt not in base_set and stmt not in onto_set:
            derived.add(stmt)
    return derived


def validate(
    store: GraphStore,
    shape_graph: str | Path | None = None,
) -> ValidationReport:
    """Validate a store against a SHACL shape graph.

    Thin alias over :meth:`cataforge.kg.store.GraphStore.validate` so calling
    code can express "I'm running the reasoning layer" intent at the import
    site rather than reaching into the store backend directly."""
    return store.validate(shape_graph)
