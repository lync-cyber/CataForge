"""Task ← Module decomposes adapter — DEV-PLAN-side (tech-lead).

Pre-dispatch loads the upstream ARCH modules plus tasks already declared
in the current DEV-PLAN. Write-back materialises each ``output.tasks``
item as a typed ``cfa:Task`` linked back to its parent module via
``cfa:decomposes``."""

from __future__ import annotations

from typing import Any, ClassVar

from cataforge.kg.adapters.base import SchemaDrivenAdapter


class TaskDecomposeAdapter(SchemaDrivenAdapter):
    """Author ``cfa:Task`` nodes + ``cfa:decomposes`` edges."""

    name: ClassVar[str] = "task_decompose"

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "doc_id_param": {"type": "string", "default": "doc_id"},
            "upstream_doc_param": {
                "type": "string",
                "default": "arch_doc_iri",
            },
            "pre_dispatch_queries": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "write_back_schema": {"type": "string"},
        },
        "required": ["pre_dispatch_queries", "write_back_schema"],
    }
