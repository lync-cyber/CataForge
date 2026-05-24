"""Read-only adapter — used by reviewer / reflector / debugger / qa-engineer.

Surfaces context from the KG into the prompt but never mutates the
store. ``write_back`` is the empty list; if an agent declares this
adapter but emits structured output anyway, the data is ignored
(intentionally — the read-only contract is enforced at the adapter,
not at the agent prompt)."""

from __future__ import annotations

from typing import Any, ClassVar

from cataforge.kg.adapters.base import AdapterError, KGAdapter
from cataforge.kg.store import Triple


class DocReadAdapter(KGAdapter):
    """Inject KG context, never write back."""

    name: ClassVar[str] = "doc_read"

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "doc_id_param": {"type": "string", "default": "doc_id"},
            "pre_dispatch_queries": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["pre_dispatch_queries"],
    }

    def pre_dispatch_context(self, params: dict[str, Any]) -> dict[str, Any]:
        queries = self.config.get("pre_dispatch_queries") or {}
        results: dict[str, Any] = {}
        for key, sparql in queries.items():
            if not isinstance(sparql, str):
                raise AdapterError(
                    f"pre_dispatch_queries.{key} must be a SPARQL string",
                )
            results[key] = self.run_query(sparql, params)
        return results

    def write_back(self, agent_output: dict[str, Any]) -> list[Triple]:
        del agent_output  # read-only adapter ignores output
        return []
