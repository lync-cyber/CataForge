"""Tests for kg query SPARQL write-guard (A3) and result materialisation (A1)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ------------------------------------------------------------------
# A3 — write-operation guard
# ------------------------------------------------------------------


class TestSparqlWriteGuard:
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
        from cataforge.cli.kg_cmd import _guard_sparql_writes
        from cataforge.core.errors import CataforgeError

        with pytest.raises(CataforgeError, match="writes are not supported"):
            _guard_sparql_writes(sparql)

    @pytest.mark.parametrize(
        "sparql",
        [
            "PREFIX cf: <https://cataforge.dev/ontology/> SELECT ?s WHERE { ?s ?p ?o }",
            "ASK { ?s ?p ?o }",
            "DESCRIBE <urn:x>",
            "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
            # PREFIX declarations before SELECT must not be misidentified
            "PREFIX ex: <http://example.org/>\nPREFIX cf: <https://cataforge.dev/ontology/>\n"
            "SELECT ?eid WHERE { ?s cf:entity_id ?eid }",
        ],
    )
    def test_read_operations_pass_through(self, sparql: str) -> None:
        from cataforge.cli.kg_cmd import _guard_sparql_writes

        # Must not raise
        _guard_sparql_writes(sparql)

    def test_write_with_prefix_declarations_is_still_rejected(self) -> None:
        from cataforge.cli.kg_cmd import _guard_sparql_writes
        from cataforge.core.errors import CataforgeError

        sparql = "PREFIX ex: <http://example.org/>\nINSERT DATA { ex:a ex:b ex:c }"
        with pytest.raises(CataforgeError, match="writes are not supported"):
            _guard_sparql_writes(sparql)

    def test_write_with_leading_comment_is_rejected(self) -> None:
        from cataforge.cli.kg_cmd import _guard_sparql_writes
        from cataforge.core.errors import CataforgeError

        sparql = "# This is a comment\nDELETE DATA { <urn:a> <urn:b> <urn:c> }"
        with pytest.raises(CataforgeError, match="writes are not supported"):
            _guard_sparql_writes(sparql)


# ------------------------------------------------------------------
# A1 — _materialize_query_result does not drop rows on large results
# ------------------------------------------------------------------


class TestMaterializeQueryResult:
    def _make_mock_solutions(self, n_rows: int):
        """Build a mock QuerySolutions object with n_rows rows."""
        from pyoxigraph import Variable  # type: ignore[import]

        var_x = Variable("x")
        var_y = Variable("y")

        mock_raw = MagicMock()
        mock_raw.__class__.__name__ = "QuerySolutions"
        # variables is a list — once materialised it should be stable
        mock_raw.variables = [var_x, var_y]

        rows = []
        for i in range(n_rows):
            row = MagicMock()
            row.__getitem__ = lambda self, v, _i=i: MagicMock(
                __class__=type("Literal", (), {"value": str(_i)})(),
            )
            rows.append(row)

        mock_raw.__iter__ = MagicMock(return_value=iter(rows))
        return mock_raw

    def test_large_result_set_row_count_is_preserved(self) -> None:
        from cataforge.cli.kg_cmd import _materialize_query_result

        n = 500
        mock_raw = MagicMock()
        mock_raw.__class__.__name__ = "QuerySolutions"

        try:
            from pyoxigraph import Variable  # type: ignore[import]

            var_x = Variable("x")
        except ImportError:
            pytest.skip("pyoxigraph not available")

        mock_raw.variables = [var_x]

        rows = []
        for i in range(n):
            row = MagicMock()

            def _getitem(v, _i=i):
                m = MagicMock()
                m.__class__.__name__ = "Literal"
                m.value = str(_i)
                return m

            row.__getitem__ = _getitem
            rows.append(row)

        mock_raw.__iter__ = MagicMock(return_value=iter(rows))

        kind, variables, result_rows = _materialize_query_result(mock_raw)  # type: ignore[misc]

        assert kind == "select"
        assert len(result_rows) == n, f"expected {n} rows, got {len(result_rows)}"

    def test_variables_consumed_only_once(self) -> None:
        """variables must be read before the row loop, not inside it."""
        from cataforge.cli.kg_cmd import _materialize_query_result

        try:
            from pyoxigraph import Variable  # type: ignore[import]

            var_a = Variable("a")
        except ImportError:
            pytest.skip("pyoxigraph not available")

        call_count = 0

        class _VariablesList:
            def __iter__(self):
                nonlocal call_count
                call_count += 1
                return iter([var_a])

        mock_raw = MagicMock()
        mock_raw.__class__.__name__ = "QuerySolutions"
        mock_raw.variables = _VariablesList()

        row = MagicMock()
        val = MagicMock()
        val.__class__.__name__ = "Literal"
        val.value = "hello"
        row.__getitem__ = lambda _self, _v: val
        mock_raw.__iter__ = MagicMock(return_value=iter([row]))

        _materialize_query_result(mock_raw)

        assert call_count == 1, (
            f"variables iterated {call_count} times; expected exactly 1 "
            "(must be materialised before row loop)"
        )
