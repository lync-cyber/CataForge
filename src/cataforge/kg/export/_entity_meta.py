"""Shared metadata for the KG → Markdown export path.

Two related pipeline files (`pipeline.py` for full-store export,
`render.py` for single-entity rendering used by the shim) both need
the same entity-type → doc-type mapping, the same relation-group
projection (used to fold multi-row SPARQL results back into Jinja
context lists), and the same template-name resolution. They lived
in `pipeline.py` originally; moving them here lets `render.py` import
without a sibling-private-symbol detour.
"""

from __future__ import annotations

_ENTITY_TYPE_TO_DOC_TYPE: dict[str, str] = {
    "Feature": "prd",
    "AcceptanceCriteria": "prd",
    "UserStory": "prd",
    "Epic": "prd",
    "Module": "arch",
    "Component": "arch",
    "API": "arch",
    "DataModel": "arch",
    "ArchitectureDecision": "arch",
    "TechStack": "arch",
    "Page": "ui-spec",
    "Wireframe": "ui-spec",
    "UIComponent": "ui-spec",
    "UserFlow": "ui-spec",
    "Task": "dev-plan",
    "Subtask": "dev-plan",
    "TestCase": "test-report",
    "TestSuite": "test-report",
    "TestPlan": "test-report",
    "TestRun": "test-report",
}


_RELATION_GROUPS: dict[str, dict[str, tuple[str, ...]]] = {
    "feature": {
        "acceptance_criteria": ("ac_id", "ac_sort_key", "ac_title"),
        "implementations": ("impl_id", "impl_sort_key", "impl_title"),
        "verifications": ("tc_id", "tc_sort_key", "tc_title"),
    },
    "acceptancecriteria": {
        "features": ("feature_id", "feature_sort_key", "feature_title"),
        "verifications": ("tc_id", "tc_sort_key", "tc_title"),
    },
    "module": {
        "implements": ("req_id", "req_sort_key", "req_title"),
        "tasks": ("task_id", "task_sort_key", "task_title"),
    },
    "testcase": {
        "verifies": ("target_id", "target_sort_key", "target_title"),
    },
    "techstack": {
        "stack_layers": ("stack_layer",),
    },
}


def _entity_type_to_doc_type(entity_type: str) -> str:
    return _ENTITY_TYPE_TO_DOC_TYPE.get(entity_type, "misc")


def _template_name(entity_type: str) -> str:
    return f"{_entity_type_to_doc_type(entity_type)}/{entity_type.lower()}.md.j2"


__all__ = [
    "_ENTITY_TYPE_TO_DOC_TYPE",
    "_RELATION_GROUPS",
    "_entity_type_to_doc_type",
    "_template_name",
]
