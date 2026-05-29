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
    "Glossary": "prd",
    "Risk": "prd",
    "Module": "arch",
    "Component": "arch",
    "API": "arch",
    "DataModel": "arch",
    "ArchitectureDecision": "arch",
    "TechStack": "arch",
    "Interface": "arch",
    "Page": "ui-spec",
    "Wireframe": "ui-spec",
    "UIComponent": "ui-spec",
    "UserFlow": "ui-spec",
    "Task": "dev-plan",
    "Subtask": "dev-plan",
    "Sprint": "dev-plan",
    "Iteration": "dev-plan",
    "Milestone": "dev-plan",
    "TestCase": "test-report",
    "TestSuite": "test-report",
    "TestPlan": "test-report",
    "TestRun": "test-report",
    "CoverageRule": "test-report",
    "Deployment": "deploy-spec",
    "Pipeline": "deploy-spec",
    "Environment": "deploy-spec",
    "Release": "deploy-spec",
}

# Generic template + SPARQL registry key used when an entity class has no
# bespoke template. The generic Jinja template extends the same artifact
# base, so any SoftwareArtifact subclass renders its core slots without a
# per-class file.
GENERIC_TEMPLATE_NAME = "_base/artifact.md.j2"
GENERIC_SPARQL_KEY = "_artifact"


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


def resolve_template(jinja_env: object, entity_type: str, override: str | None = None) -> object:
    """Return the Jinja template for `entity_type`, falling back to generic.

    Classes with a bespoke `{doc_type}/{class}.md.j2` use it; any other
    SoftwareArtifact subclass renders through `GENERIC_TEMPLATE_NAME`.
    """
    from jinja2 import TemplateNotFound

    name = override or _template_name(entity_type)
    try:
        return jinja_env.get_template(name)  # type: ignore[attr-defined]
    except TemplateNotFound:
        return jinja_env.get_template(GENERIC_TEMPLATE_NAME)  # type: ignore[attr-defined]


__all__ = [
    "GENERIC_SPARQL_KEY",
    "GENERIC_TEMPLATE_NAME",
    "_ENTITY_TYPE_TO_DOC_TYPE",
    "_RELATION_GROUPS",
    "_entity_type_to_doc_type",
    "_template_name",
    "resolve_template",
]
