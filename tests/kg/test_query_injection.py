"""SPARQL injection guard tests for _dsl_to_sparql and coverage."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from cataforge.kg.query import QueryError, coverage, q
from cataforge.kg.store import RDFLibStore, Triple


@pytest.fixture
def store(tmp_path) -> Iterator[RDFLibStore]:
    s = RDFLibStore()
    s.load(tmp_path)
    s.add([
        Triple("cfa:prd/F-001", "rdf:type", "cfa:Feature"),
        Triple("cfa:test/TC-001", "rdf:type", "cfa:TestCase"),
        Triple("cfa:test/TC-001", "cfa:validates", "cfa:prd/F-001"),
    ])
    yield s


# ---------- _dsl_to_sparql injection ----------

def test_src_type_injection_rejected(store: RDFLibStore) -> None:
    with pytest.raises(QueryError, match=r"invalid.*src_type"):
        q(store, dsl={
            "rel": "cfa:validates",
            "src_type": 'cfa:Feature } BIND("PWNED" AS ?x) { ',
        })


def test_src_type_bare_keyword_rejected(store: RDFLibStore) -> None:
    with pytest.raises(QueryError, match=r"invalid.*src_type"):
        q(store, dsl={"rel": "cfa:validates", "src_type": "DROP ALL"})


def test_dst_type_injection_rejected(store: RDFLibStore) -> None:
    with pytest.raises(QueryError, match=r"invalid.*dst_type"):
        q(store, dsl={
            "rel": "cfa:validates",
            "dst_type": 'Feature" ; DELETE { ?s ?p ?o } WHERE { ?s ?p ?o } ; SELECT "',
        })


def test_rel_injection_rejected(store: RDFLibStore) -> None:
    with pytest.raises(QueryError, match=r"invalid.*rel"):
        q(store, dsl={"rel": "cfa:validates } INSERT { <x:y> <x:y> <x:y> } WHERE { "})


def test_valid_dsl_produces_correct_sparql(store: RDFLibStore) -> None:
    rows = q(store, dsl={
        "rel": "cfa:validates",
        "src_type": "cfa:TestCase",
        "dst_type": "cfa:Feature",
    })
    assert len(rows) == 1
    assert rows[0]["dst"].endswith("prd/F-001")
    assert rows[0]["src"].endswith("test/TC-001")


# ---------- coverage injection ----------

def test_coverage_rows_class_injection_rejected(store: RDFLibStore) -> None:
    with pytest.raises(QueryError, match=r"invalid.*rows_class"):
        coverage(
            store,
            rows_class='cfa:Feature } INSERT { <x:y> <x:p> <x:o> } WHERE { ?x a cfa:Feature',
            cols_class="cfa:TestCase",
            via="cfa:validates",
        )


def test_coverage_cols_class_injection_rejected(store: RDFLibStore) -> None:
    with pytest.raises(QueryError, match=r"invalid.*cols_class"):
        coverage(
            store,
            rows_class="cfa:Feature",
            cols_class="DROP ALL",
            via="cfa:validates",
        )


def test_coverage_via_injection_rejected(store: RDFLibStore) -> None:
    with pytest.raises(QueryError, match=r"invalid.*via"):
        coverage(
            store,
            rows_class="cfa:Feature",
            cols_class="cfa:TestCase",
            via="cfa:validates } DELETE { ?s ?p ?o } WHERE { ?s ?p ?o } ; SELECT ?x WHERE { ?x a",
        )


def test_coverage_valid_args_produce_matrix(store: RDFLibStore) -> None:
    matrix = coverage(
        store,
        rows_class="cfa:Feature",
        cols_class="cfa:TestCase",
        via="cfa:validates",
        direction="col_to_row",
    )
    assert ("cfa:prd/F-001", "cfa:test/TC-001") in matrix.cells
    assert matrix.covered_cells == 1
    assert matrix.total_cells == 1
