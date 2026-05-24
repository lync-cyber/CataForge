"""Module → Feature implements adapter — ARCH-side (architect).

Pre-dispatch loads the upstream PRD's features (so the LLM knows what
needs implementing) plus the modules already declared in the current
ARCH doc. Write-back materialises each ``output.modules`` item as a
typed ``cfa:Module`` and emits the ``cfa:implements`` edge to the
feature(s) it covers."""

from __future__ import annotations

from typing import Any, ClassVar

from cataforge.kg.adapters.base import SchemaDrivenAdapter


class ModuleImplementsAdapter(SchemaDrivenAdapter):
    """Author / refine ``cfa:Module`` nodes + ``cfa:implements`` edges."""

    name: ClassVar[str] = "module_implements"

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "doc_id_param": {"type": "string", "default": "doc_id"},
            "upstream_doc_param": {
                "type": "string",
                "default": "prd_doc_iri",
                "description":
                    "Name of the param holding the PRD doc IRI from which "
                    "the LLM should source feature IDs to implement.",
            },
            "pre_dispatch_queries": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "write_back_schema": {"type": "string"},
        },
        "required": ["pre_dispatch_queries", "write_back_schema"],
    }
