"""Feature authoring adapter — PRD-side (product-manager, architect).

Pre-dispatch surfaces the features already declared in the doc plus the
list of downstream consumers (so the LLM doesn't accidentally rename an
ID that something else still references). Write-back materialises each
feature in ``output.features`` into a typed Feature node with label /
id / optional status, linked to the parent document via
``cfk:definedIn``."""

from __future__ import annotations

from typing import Any, ClassVar

from cataforge.kg.adapters.base import SchemaDrivenAdapter


class FeatureAuthoringAdapter(SchemaDrivenAdapter):
    """Author / refine ``cfa:Feature`` nodes inside a PRD document."""

    name: ClassVar[str] = "feature_authoring"

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "doc_id_param": {
                "type": "string",
                "default": "doc_id",
                "description":
                    "Name of the param in pre_dispatch_context whose value "
                    "is the doc identifier (used to scope the queries).",
            },
            "pre_dispatch_queries": {
                "type": "object",
                "additionalProperties": {"type": "string"},
                "description":
                    "Mapping of context key → SPARQL string. The string "
                    "may reference $doc_id / $doc_iri via string.Template "
                    "substitution.",
            },
            "write_back_schema": {
                "type": "string",
                "description":
                    "Project-relative path to the JSON file that maps "
                    "agent output → triples (see triples_from_schema).",
            },
        },
        "required": ["pre_dispatch_queries", "write_back_schema"],
    }
