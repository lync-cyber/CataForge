"""Component → Feature renders adapter — UI-SPEC-side (ui-designer).

Pre-dispatch loads PRD features (which the UI must surface) plus
components already declared in the current UI-SPEC. Write-back
materialises each ``output.components`` item as a typed ``cfa:Component``
linked to the feature(s) it visualises via ``cfa:renders``."""

from __future__ import annotations

from typing import Any, ClassVar

from cataforge.kg.adapters.base import SchemaDrivenAdapter


class UIRendersAdapter(SchemaDrivenAdapter):
    """Author ``cfa:Component`` nodes + ``cfa:renders`` edges."""

    name: ClassVar[str] = "ui_renders"

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "doc_id_param": {"type": "string", "default": "doc_id"},
            "upstream_doc_param": {
                "type": "string",
                "default": "prd_doc_iri",
            },
            "pre_dispatch_queries": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "write_back_schema": {"type": "string"},
        },
        "required": ["pre_dispatch_queries", "write_back_schema"],
    }
