"""Deterministic entity-id → IRI mapping for the ingest pipeline.

Entity IRIs derive deterministically from the entity-id string so a
re-run produces identical subjects and the ASK-dedup pass treats them
as already present.

The prefix → class-name map mirrors the canonical schema at
`src/cataforge/domain/kg/schemas/core.yaml` (and governance.yaml). The schema
is the source of truth; a regression test pins consistency against the
live `SchemaView`.
"""

from __future__ import annotations

import re

from cataforge.domain.kg._sparql_utils import escape_iri_component

# Maps entity-id prefix → core.yaml class name. The prefix portion is the
# longest leading uppercase run before the dash; entity_ids must be
# unambiguous (the regex `^[A-Z]+-` anchored against the prefix table).
ENTITY_PREFIX_TO_CLASS: dict[str, str] = {
    "F": "Feature",
    "AC": "AcceptanceCriteria",
    "M": "Module",
    "API": "API",
    "E": "DataModel",
    "C": "Component",
    "UC": "UIComponent",
    "P": "Page",
    "T": "Task",
    "TC": "TestCase",
    "TS": "TechStack",
    "SR": "SprintReviewIssue",
    "ADR": "ArchitectureDecision",
    "US": "UserStory",
    "EP": "Epic",
    "REL": "Release",
    "DP": "Deployment",
    "PL": "Pipeline",
    "ENV": "Environment",
    "GL": "Glossary",
    "RK": "Risk",
    "CHG": "ChangeRequest",
    "REV": "ReviewReport",
    "TP": "TestPlan",
    "TS_": "TestSuite",  # explicit prefix — prevents TS from capturing TestSuite IDs
    "TR": "TestRun",
    "CR": "CoverageRule",
    "MS": "Milestone",
    "WF": "Wireframe",
    "UF": "UserFlow",
    "IF": "Interface",
    "ST": "Subtask",
    "S": "Sprint",
    "I": "Iteration",
    "Phase": "Phase",  # arch §1 Phase IDs may use the word "Phase" — left as edge case
}

DEFAULT_ONTOLOGY_NS = "https://cataforge.dev/ontology/"
DEFAULT_INSTANCE_NS = "https://cataforge.dev/instance/"

_PREFIX_RE = re.compile(r"^([A-Z]+(?:-[A-Z]+)*?|[A-Z]+)-\d+$")


def id_prefix_to_type(entity_id: str) -> str | None:
    """Return the schema class name for an entity_id like `F-001`, or None.

    Resolution order: try the longest prefix that matches the table, so
    `API-001` resolves to `API` even though `A` would also be a (non-existent)
    prefix.
    """
    m = _PREFIX_RE.match(entity_id)
    if not m:
        return None
    prefix = m.group(1)
    # Try the full prefix first, then fall back to single-char roots for
    # robustness in case the entity_id uses an unusual delimiter.
    if prefix in ENTITY_PREFIX_TO_CLASS:
        return ENTITY_PREFIX_TO_CLASS[prefix]
    return None


def entity_iri(entity_id: str, base_namespace: str = DEFAULT_INSTANCE_NS) -> str:
    """Return the canonical instance IRI for an entity_id."""
    if not entity_id or len(entity_id) > 256:
        raise ValueError(f"invalid entity_id: {entity_id!r}")
    return f"{base_namespace.rstrip('/')}/{escape_iri_component(entity_id)}"


def class_iri(class_name: str, ontology_namespace: str = DEFAULT_ONTOLOGY_NS) -> str:
    """Return the canonical ontology IRI for a class name."""
    if not class_name or len(class_name) > 256:
        raise ValueError(f"invalid class_name: {class_name!r}")
    return f"{ontology_namespace.rstrip('/')}/{escape_iri_component(class_name)}"


def document_iri(doc_id: str, base_namespace: str = DEFAULT_INSTANCE_NS) -> str:
    """Return the canonical instance IRI for a Document node.

    Structural nodes live under a `/doc/` path segment so they never
    collide with entity IRIs (which sit directly under the base namespace).
    """
    if not doc_id or len(doc_id) > 256:
        raise ValueError(f"invalid doc_id: {doc_id!r}")
    return f"{base_namespace.rstrip('/')}/doc/{escape_iri_component(doc_id)}"


def section_iri(doc_id: str, anchor: str, base_namespace: str = DEFAULT_INSTANCE_NS) -> str:
    """Return the canonical instance IRI for a Section node.

    Identity is `(doc_id, anchor)`; deterministic so a re-ingest of the
    same section produces the same subject.
    """
    if not doc_id or not anchor or len(doc_id) + len(anchor) > 512:
        raise ValueError(f"invalid section identity: {doc_id!r} / {anchor!r}")
    return (
        f"{base_namespace.rstrip('/')}/doc/"
        f"{escape_iri_component(doc_id)}/sec/{escape_iri_component(anchor)}"
    )
