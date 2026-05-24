"""C1 query helpers — SPARQL/DSL/Cypher-lite/impact/explain/coverage."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from cataforge.kg.query import (
    COVERAGE_PRESETS,
    CoverageMatrix,
    coverage,
    cypher_lite,
    explain,
    impact,
    q,
)
from cataforge.kg.store import RDFLibStore, Triple


@pytest.fixture
def populated_store(tmp_path) -> Iterator[RDFLibStore]:
    """A small store with PRD/Arch/Test triples sufficient for query tests."""
    store = RDFLibStore()
    store.load(tmp_path)
    store.add([
        # Features
        Triple("cfa:prd/F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd/F-001", "cfk:hasId", "F-001"),
        Triple("cfa:prd/F-002", "rdf:type", "cfa:Feature"),
        Triple("cfa:prd/F-002", "cfk:hasId", "F-002"),
        # Modules + implements
        Triple("cfa:arch/M-001", "rdf:type", "cfa:Module"),
        Triple("cfa:arch/M-001", "cfk:hasId", "M-001"),
        Triple("cfa:arch/M-001", "cfa:realizes", "cfa:prd/F-001"),
        # CodeUnit
        Triple("cfa:src/CU-001", "rdf:type", "cfa:CodeUnit"),
        Triple("cfa:src/CU-001", "cfa:implements", "cfa:arch/M-001"),
        # TestCases (RTM source)
        Triple("cfa:test/TC-001", "rdf:type", "cfa:TestCase"),
        Triple("cfa:test/TC-001", "cfa:validates", "cfa:prd/F-001"),
        # Dependency chain for impact
        Triple("cfa:dep/A", "cfa:dependsOn", "cfa:dep/B"),
        Triple("cfa:dep/B", "cfa:dependsOn", "cfa:dep/C"),
    ])
    yield store


# ---------- q ----------

def test_q_sparql_passthrough(populated_store: RDFLibStore) -> None:
    rows = q(
        populated_store,
        sparql="SELECT ?x WHERE { ?x a cfa:Feature } ORDER BY ?x",
    )
    assert len(rows) == 2


def test_q_dsl_relation_match(populated_store: RDFLibStore) -> None:
    rows = q(
        populated_store,
        dsl={
            "rel": "cfa:realizes",
            "src_type": "cfa:Module",
            "dst_type": "cfa:Feature",
        },
    )
    assert len(rows) == 1
    assert rows[0]["dst"].endswith("prd/F-001")


def test_q_dsl_filter_by_dst(populated_store: RDFLibStore) -> None:
    rows = q(
        populated_store,
        dsl={
            "rel": "cfa:realizes",
            "dst": "cfa:prd/F-001",
        },
    )
    assert len(rows) == 1


def test_q_rejects_both_args(populated_store: RDFLibStore) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        q(populated_store, sparql="ASK { ?x ?p ?o }", dsl={"rel": "cfa:implements"})


def test_q_rejects_neither_arg(populated_store: RDFLibStore) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        q(populated_store)


def test_dsl_requires_rel(populated_store: RDFLibStore) -> None:
    with pytest.raises(ValueError, match="'rel'"):
        q(populated_store, dsl={"src_type": "cfa:Module"})


# ---------- cypher_lite ----------

def test_cypher_lite_single_pattern(populated_store: RDFLibStore) -> None:
    rows = cypher_lite(
        populated_store,
        "MATCH (a:Module)-[:realizes]->(b:Feature) RETURN a, b",
    )
    assert rows and rows[0]["a"].endswith("M-001")
    assert rows[0]["b"].endswith("F-001")


def test_cypher_lite_rejects_multi_pattern(populated_store: RDFLibStore) -> None:
    with pytest.raises(ValueError, match="single-pattern"):
        cypher_lite(
            populated_store,
            "MATCH (a:Module)-[:realizes]->(b:Feature),(c:Task)-[:decomposes]->(a) RETURN a",
        )


def test_cypher_lite_bare_type_gets_cfa_prefix(populated_store: RDFLibStore) -> None:
    # "Module" without prefix should default to "cfa:Module".
    rows = cypher_lite(
        populated_store,
        "MATCH (a:Module)-[:realizes]->(b:Feature) RETURN a",
    )
    assert rows


# ---------- impact ----------

def test_impact_transitive_closure(populated_store: RDFLibStore) -> None:
    # A depends on B; B depends on C. So B and A both impact C.
    deps_of_c = impact(populated_store, "cfa:dep/C")
    assert set(deps_of_c) == {"cfa:dep/A", "cfa:dep/B"}


def test_impact_isolated_node_returns_empty(populated_store: RDFLibStore) -> None:
    populated_store.add([Triple("cfa:lonely/X", "rdf:type", "cfa:Feature")])
    assert impact(populated_store, "cfa:lonely/X") == []


# ---------- explain ----------

def test_explain_base_assertion(populated_store: RDFLibStore) -> None:
    result = explain(
        populated_store, "cfa:arch/M-001", "cfa:realizes", "cfa:prd/F-001",
    )
    assert result.derivation == "base"


def test_explain_absent_triple(populated_store: RDFLibStore) -> None:
    result = explain(
        populated_store, "cfa:arch/M-001", "cfa:realizes", "cfa:prd/F-002",
    )
    assert result.derivation == "absent"


# ---------- coverage ----------

def test_coverage_rtm_preset(populated_store: RDFLibStore) -> None:
    matrix = coverage(populated_store, preset="rtm",
                      rows_class="", cols_class="", via="")
    assert isinstance(matrix, CoverageMatrix)
    # F-001 is covered by TC-001; F-002 has no test → gap.
    assert ("cfa:prd/F-001", "cfa:test/TC-001") in matrix.cells
    assert "cfa:prd/F-002" in matrix.gaps


def test_coverage_explicit_args(populated_store: RDFLibStore) -> None:
    matrix = coverage(
        populated_store,
        rows_class="cfa:Feature",
        cols_class="cfa:TestCase",
        via="cfa:validates",
        direction="col_to_row",
    )
    assert matrix.coverage_ratio > 0
    assert matrix.coverage_ratio < 1.0  # F-002 is a gap


def test_coverage_row_to_col_direction(populated_store: RDFLibStore) -> None:
    # Module → Feature direction via realizes; col-to-row would invert it.
    matrix = coverage(
        populated_store,
        rows_class="cfa:Module",
        cols_class="cfa:Feature",
        via="cfa:realizes",
        direction="row_to_col",
    )
    assert ("cfa:arch/M-001", "cfa:prd/F-001") in matrix.cells


def test_coverage_unknown_preset_raises(populated_store: RDFLibStore) -> None:
    with pytest.raises(ValueError, match="unknown coverage preset"):
        coverage(populated_store, preset="bogus",
                 rows_class="", cols_class="", via="")


def test_coverage_unknown_direction_raises(populated_store: RDFLibStore) -> None:
    with pytest.raises(ValueError, match="unknown direction"):
        coverage(
            populated_store,
            rows_class="cfa:Feature", cols_class="cfa:TestCase",
            via="cfa:validates", direction="sideways",
        )


def test_coverage_ratio_and_total(populated_store: RDFLibStore) -> None:
    matrix = coverage(populated_store, preset="rtm",
                      rows_class="", cols_class="", via="")
    # 2 features × 1 test = 2 cells; 1 covered → 0.5
    assert matrix.total_cells == 2
    assert matrix.covered_cells == 1
    assert matrix.coverage_ratio == 0.5


def test_coverage_presets_complete() -> None:
    for required in ("rtm", "test", "risk", "interface"):
        assert required in COVERAGE_PRESETS
