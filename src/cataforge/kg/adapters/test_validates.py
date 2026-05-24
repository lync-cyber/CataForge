"""TestCase → Feature validates adapter — test author / qa-engineer side.

Pre-dispatch loads features from the PRD plus TestCases already declared
in the current test doc. Write-back materialises each
``output.test_cases`` item as a typed ``cfa:TestCase`` linked to the
feature(s) it covers via ``cfa:validates``."""

from __future__ import annotations

from typing import Any, ClassVar

from cataforge.kg.adapters.base import SchemaDrivenAdapter


class TestValidatesAdapter(SchemaDrivenAdapter):
    """Author ``cfa:TestCase`` nodes + ``cfa:validates`` edges."""

    # Tell pytest not to collect this class as test cases — the ``Test``
    # prefix is unfortunate but matches design §3.3's adapter naming.
    __test__ = False

    name: ClassVar[str] = "test_validates"

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
