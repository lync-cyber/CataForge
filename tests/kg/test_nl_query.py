"""Tests for the natural-language → SPARQL read-only query surface.

The LLM is stubbed with a fixed reply, so these exercise the deterministic
half — schema-card prompt → SPARQL extraction → read-only gate → read path —
without any network or model dependency.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.core.errors import CataforgeError

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


class _FakeLLM:
    """Minimal stub: returns a fixed reply to every `.invoke()`."""

    def __init__(self, reply: str) -> None:
        self._reply = reply

    def invoke(self, _prompt: str) -> str:
        return self._reply


class _ScriptedLLM:
    """Returns queued replies in order, one per `.invoke()` — for the two-call
    `answer()` path (translate, then summarize)."""

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)

    def invoke(self, _prompt: str) -> str:
        return self._replies.pop(0)


def _open_and_ingest(variant: str):
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, FIXTURE_ROOT / variant, config)
    return KnowledgeGraph(handle.raw, config), config


def test_translate_extracts_sparql_from_fenced_block() -> None:
    from cataforge.domain.kg.nl_query import translate

    llm = _FakeLLM("Sure:\n```sparql\nSELECT ?s WHERE { ?s ?p ?o }\n```\n")
    assert translate("anything", llm) == "SELECT ?s WHERE { ?s ?p ?o }"


def test_query_endtoend_with_mock_llm() -> None:
    from cataforge.domain.kg.nl_query import query

    kg, _ = _open_and_ingest("waterfall")
    sparql = (
        "PREFIX cf: <https://cataforge.dev/ontology/> "
        "SELECT ?id WHERE { ?f a cf:Feature ; cf:entity_id ?id } ORDER BY ?id"
    )
    llm = _FakeLLM(f"```sparql\n{sparql}\n```")

    result = query(kg, "list every feature", llm)

    assert result.columns == ["id"]
    assert "F-001" in [r["id"] for r in result.rows]
    assert "LIMIT" in result.sparql.upper()


def test_query_rejects_llm_emitted_write() -> None:
    from cataforge.domain.kg.nl_query import query

    kg, _ = _open_and_ingest("waterfall")
    llm = _FakeLLM("INSERT DATA { <urn:a> <urn:b> <urn:c> }")

    with pytest.raises(CataforgeError, match="writes are not supported"):
        query(kg, "wipe the graph", llm)


def test_query_ask_returns_boolean_row() -> None:
    from cataforge.domain.kg.nl_query import query

    kg, _ = _open_and_ingest("waterfall")
    llm = _FakeLLM("PREFIX cf: <https://cataforge.dev/ontology/> ASK { ?f a cf:Feature }")

    result = query(kg, "are there any features?", llm)

    assert result.columns == ["result"]
    assert result.rows == [{"result": "true"}]


def test_answer_summarizes_query_rows() -> None:
    from cataforge.domain.kg.nl_query import answer

    kg, _ = _open_and_ingest("waterfall")
    sparql = (
        "PREFIX cf: <https://cataforge.dev/ontology/> "
        "SELECT ?id WHERE { ?f a cf:Feature ; cf:entity_id ?id } ORDER BY ?id"
    )
    # First invoke → SPARQL; second invoke → prose over the resulting rows.
    llm = _ScriptedLLM(f"```sparql\n{sparql}\n```", "The graph defines feature F-001.")

    out = answer(kg, "list every feature", llm)

    assert out == "The graph defines feature F-001."


def test_answer_inherits_read_only_guard() -> None:
    from cataforge.domain.kg.nl_query import answer

    kg, _ = _open_and_ingest("waterfall")
    # A single scripted reply: the write must be rejected by query()'s gate
    # before any summarization invoke is reached.
    llm = _ScriptedLLM("INSERT DATA { <urn:a> <urn:b> <urn:c> }")

    with pytest.raises(CataforgeError, match="writes are not supported"):
        answer(kg, "wipe the graph", llm)
