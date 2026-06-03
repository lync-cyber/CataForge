"""Optional natural-language → SPARQL read-only query surface.

Query-layer only and strictly read-only: an LLM translates a question into a
SPARQL string, which is gate-checked to SELECT/ASK by
`read_query.assert_read_only` and run through the existing pyoxigraph read
path. It never touches ingest/export — the deterministic core stays LLM-free.

`translate()` / `query()` only need an object exposing `.invoke(prompt)` (the
LangChain language-model contract), so the core path does not import LangChain;
install `cataforge[llm]` for a concrete model. `answer()` is a thin convenience
wrapper over LangChain's `GraphSparqlQAChain`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from cataforge.domain.kg._sparql_utils import _row_lookup, _strv
from cataforge.domain.kg.read_query import assert_read_only, inject_limit
from cataforge.domain.kg.schema_context import build_schema_card

if TYPE_CHECKING:
    from cataforge.domain.kg import KnowledgeGraph


class LanguageModel(Protocol):
    """Minimal contract a caller's LLM must satisfy (LangChain-compatible)."""

    def invoke(self, prompt: str) -> Any: ...


_SPARQL_FENCE_RE = re.compile(r"```(?:sparql)?\s*(.+?)```", re.DOTALL | re.IGNORECASE)

_PROMPT_TEMPLATE = (
    "{schema_card}\n"
    "Translate the question into a single read-only SPARQL query "
    "(SELECT or ASK only; never INSERT/DELETE/UPDATE). Return only the query.\n\n"
    "Question: {question}\nSPARQL:"
)


def _extract_sparql(text: str) -> str:
    """Pull a SPARQL body out of an LLM reply — fenced code block or raw text."""
    match = _SPARQL_FENCE_RE.search(text)
    return (match.group(1) if match else text).strip()


def _llm_text(response: Any) -> str:
    """Normalize a LangChain message or plain-string response to text."""
    return response.content if hasattr(response, "content") else str(response)


def translate(question: str, llm: LanguageModel, *, config: Any | None = None) -> str:
    """Translate `question` into SPARQL using `llm` grounded on the schema card."""
    prompt = _PROMPT_TEMPLATE.format(schema_card=build_schema_card(config), question=question)
    return _extract_sparql(_llm_text(llm.invoke(prompt)))


@dataclass
class NLQueryResult:
    """Structured result of a natural-language query."""

    question: str
    sparql: str
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)


def _materialize(raw: Any) -> tuple[list[str], list[dict[str, str]]]:
    """Consume a pyoxigraph SELECT/ASK result into columns + string rows."""
    if type(raw).__name__ == "QueryBoolean" or isinstance(raw, bool):
        return ["result"], [{"result": "true" if bool(raw) else "false"}]
    columns = [str(v).lstrip("?") for v in raw.variables]
    rows = [{c: (_strv(_row_lookup(sol, c)) or "") for c in columns} for sol in raw]
    return columns, rows


def query(
    kg: KnowledgeGraph,
    question: str,
    llm: LanguageModel,
    *,
    limit: int = 100,
) -> NLQueryResult:
    """Translate `question` to SPARQL and run it through the read-only path.

    The generated SPARQL is gate-checked (`assert_read_only`) before it ever
    reaches the store, so a hallucinated write is rejected rather than executed,
    then `LIMIT`-capped and run on the live store via the existing read path.
    """
    sparql = translate(question, llm, config=kg.config)
    assert_read_only(sparql)
    sparql = inject_limit(sparql, limit)
    columns, rows = _materialize(kg.store.query(sparql))
    return NLQueryResult(question=question, sparql=sparql, columns=columns, rows=rows)


def answer(kg: KnowledgeGraph, question: str, llm: LanguageModel) -> str:
    """Convenience NL answer via LangChain's `GraphSparqlQAChain`.

    Requires `cataforge[llm]`. The chain runs the LLM-generated SPARQL against an
    in-memory rdflib copy of the store (`_pyoxigraph_to_rdflib`), so a write the
    LLM might emit mutates only that throwaway copy — the live store is never
    touched. For a structured, write-guarded result over the live store, prefer
    `query()`.
    """
    from langchain.chains import GraphSparqlQAChain  # noqa: PLC0415
    from langchain_community.graphs import RdfGraph  # noqa: PLC0415

    from cataforge.domain.kg.validate import _pyoxigraph_to_rdflib  # noqa: PLC0415

    graph = RdfGraph(graph=_pyoxigraph_to_rdflib(kg.store))
    chain = GraphSparqlQAChain.from_llm(llm, graph=graph, allow_dangerous_requests=True)
    return chain.invoke({"query": f"{build_schema_card(kg.config)}\n\n{question}"})["result"]


__all__ = ["LanguageModel", "NLQueryResult", "answer", "query", "translate"]
