"""Tests for the shared read-only SPARQL policy (domain/kg/read_query.py)."""

from __future__ import annotations

import pytest

from cataforge.core.errors import CataforgeError
from cataforge.domain.kg.read_query import assert_read_only, first_sparql_keyword, inject_limit


class TestAssertReadOnly:
    @pytest.mark.parametrize(
        "sparql",
        [
            "INSERT DATA { <urn:a> <urn:b> <urn:c> }",
            "DELETE DATA { <urn:a> <urn:b> <urn:c> }",
            "UPDATE { DELETE { ?s ?p ?o } WHERE { ?s ?p ?o } }",
            "CLEAR DEFAULT",
            "DROP GRAPH <urn:g>",
            "LOAD <http://example.org/graph>",
            "CREATE GRAPH <urn:g>",
        ],
    )
    def test_write_operations_are_rejected(self, sparql: str) -> None:
        with pytest.raises(CataforgeError, match="writes are not supported"):
            assert_read_only(sparql)

    @pytest.mark.parametrize(
        "sparql",
        [
            "PREFIX cf: <https://cataforge.dev/ontology/> SELECT ?s WHERE { ?s ?p ?o }",
            "ASK { ?s ?p ?o }",
            "DESCRIBE <urn:x>",
            "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
            "PREFIX ex: <http://example.org/>\nPREFIX cf: <https://cataforge.dev/ontology/>\n"
            "SELECT ?eid WHERE { ?s cf:entity_id ?eid }",
        ],
    )
    def test_read_operations_pass_through(self, sparql: str) -> None:
        assert_read_only(sparql)  # must not raise

    def test_write_with_prefix_declarations_is_still_rejected(self) -> None:
        sparql = "PREFIX ex: <http://example.org/>\nINSERT DATA { ex:a ex:b ex:c }"
        with pytest.raises(CataforgeError, match="writes are not supported"):
            assert_read_only(sparql)

    def test_write_with_leading_comment_is_rejected(self) -> None:
        sparql = "# This is a comment\nDELETE DATA { <urn:a> <urn:b> <urn:c> }"
        with pytest.raises(CataforgeError, match="writes are not supported"):
            assert_read_only(sparql)


class TestFirstSparqlKeyword:
    def test_strips_prefix_and_comment(self) -> None:
        sparql = "# comment\nPREFIX cf: <x:>\nSELECT ?s WHERE { ?s ?p ?o }"
        assert first_sparql_keyword(sparql) == "SELECT"

    def test_empty_string(self) -> None:
        assert first_sparql_keyword("") == ""


class TestInjectLimit:
    def test_appends_limit_to_unlimited_select(self) -> None:
        out = inject_limit("SELECT ?s WHERE { ?s ?p ?o }", 50)
        assert out.endswith("LIMIT 50")

    def test_preserves_existing_limit(self) -> None:
        sparql = "SELECT ?s WHERE { ?s ?p ?o } LIMIT 5"
        assert inject_limit(sparql, 50) == sparql

    def test_leaves_ask_untouched(self) -> None:
        sparql = "ASK { ?s ?p ?o }"
        assert inject_limit(sparql, 50) == sparql
