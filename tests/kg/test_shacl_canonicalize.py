"""Unit contract for the SHACL canonicalizer's forest fast path.

`_canonicalize_shacl` must produce byte-stable, isomorphism-preserving output.
The fast path (`_blank_node_labels`) handles the forest-shaped blank-node
structure ShaclGenerator emits; a non-forest graph must fall back to rdflib's
general canonicalizer. These tests pin both branches without paying the full
linkml codegen cost.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("rdflib") is None,
    reason="rdflib not installed (shacl/all extra)",
)


def test_forest_graph_gets_unique_deterministic_labels() -> None:
    import rdflib
    from scripts.codegen_kg_schema import _blank_node_labels

    # Two node shapes, each with a structurally identical property shape —
    # the collision case that a pure content hash cannot disambiguate.
    turtle = """
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix ex: <http://example.org/> .
    ex:A a sh:NodeShape ; sh:property [ sh:datatype ex:string ; sh:minCount 1 ] .
    ex:B a sh:NodeShape ; sh:property [ sh:datatype ex:string ; sh:minCount 1 ] .
    """
    graph = rdflib.Graph()
    graph.parse(data=turtle, format="turtle")

    labels = _blank_node_labels(graph)
    assert labels is not None, "a forest graph must take the fast path"
    bnodes = [n for n in graph.all_nodes() if isinstance(n, rdflib.BNode)]
    assert len(labels) == len(bnodes)
    assert len({str(v) for v in labels.values()}) == len(bnodes), "labels must be unique"


def test_non_forest_graph_falls_back() -> None:
    import rdflib
    from scripts.codegen_kg_schema import _blank_node_labels

    # A blank node referenced by two subjects is not a forest.
    shared = rdflib.BNode()
    graph = rdflib.Graph()
    ex = rdflib.Namespace("http://example.org/")
    graph.add((ex.A, ex.p, shared))
    graph.add((ex.B, ex.p, shared))
    graph.add((shared, ex.q, rdflib.Literal("x")))

    assert _blank_node_labels(graph) is None, "shared blank node must force fallback"


def test_canonicalize_is_byte_stable_and_isomorphic() -> None:
    import rdflib
    from rdflib.compare import isomorphic
    from scripts.codegen_kg_schema import _canonicalize_shacl

    turtle = """
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix ex: <http://example.org/> .
    ex:Shape a sh:NodeShape ;
        sh:property [ sh:path ex:name ; sh:datatype ex:string ; sh:order 3 ] ;
        sh:property [ sh:path ex:age ; sh:datatype ex:int ; sh:order 1 ] .
    """
    first = _canonicalize_shacl(turtle)
    second = _canonicalize_shacl(turtle)
    assert first == second, "canonical output must be byte-stable"

    original = rdflib.Graph()
    original.parse(data=turtle, format="turtle")
    original.remove((None, rdflib.URIRef("http://www.w3.org/ns/shacl#order"), None))
    produced = rdflib.Graph()
    produced.parse(data=first, format="nt")
    assert isomorphic(produced, original), "canonical form must preserve graph semantics"
