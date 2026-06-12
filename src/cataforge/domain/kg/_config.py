"""KG connection configuration.

`KGConfig` is the single configuration object consumed by every entry point in
`cataforge.domain.kg`. The `kg_active_doc_types` default is `BUSINESS_DOC_TYPES`.
Projects that have not yet ingested into KG remain on the legacy read path
because `cataforge.domain.kg._dispatch.is_active_for()` additionally gates on
`.cataforge/kg/store/` existing on disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from cataforge.core.paths import KG_STORE_REL

# Single source of truth for the business doc_type universe. Every doc_type
# here carries entity classes the KG ingest pipeline extracts and the render
# pipeline materializes (specific template when present, generic artifact
# fallback otherwise). Entries are the canonical doc_id values that refs use
# (`prd#§2.F-001`, `test-report#§2.TC-001`), so dispatch matching on doc_id
# works directly — `test-report`, not the legacy `test` alias.
BUSINESS_DOC_TYPES: tuple[str, ...] = (
    "prd",
    "arch",
    "ui-spec",
    "dev-plan",
    "test-report",
    "deploy-spec",
)

# Default active doc_types. The doctor `kg_ingestion_completeness` gate
# enforces reconciliation for every doc_type in this set; `kg import` and the
# dispatch layer read the same set. Down-stream projects override via
# `framework.json`.
DEFAULT_KG_ACTIVE_DOC_TYPES: frozenset[str] = frozenset(BUSINESS_DOC_TYPES)

# Single source of truth for class → owning doc_type. The export pipeline
# uses it to route entities to their rendering template directory; the ingest
# pipeline derives the default definition authority from it. Cross-phase
# tracking entities are routed to the nearest owning doc_type rather than
# falling silently to misc/.
ENTITY_CLASS_TO_DOC_TYPE: dict[str, str] = {
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
    "ChangeRequest": "prd",
    "Phase": "arch",
    "SprintReviewIssue": "dev-plan",
    "ReviewReport": "test-report",
}

# Default definition authority: an entity class's definition is recognized
# only in its owning doc_type — a heading-subject or subordinate occurrence
# in any other doc_type is a reference. Projects extend (never narrow) the
# per-class set via framework.json `context.kg_definition_authority`.
DEFAULT_DEFINITION_AUTHORITY: dict[str, frozenset[str]] = {
    class_name: frozenset({doc_type}) for class_name, doc_type in ENTITY_CLASS_TO_DOC_TYPE.items()
}


@dataclass
class KGConfig:
    """Configuration for a KnowledgeGraph connection."""

    store_backend: Literal["oxigraph", "memory"] = "oxigraph"
    db_path: Path = field(default_factory=lambda: KG_STORE_REL)
    governance: bool = False
    coverage_mode: Literal["strict", "mentions"] = "strict"
    base_namespace: str = "https://cataforge.dev/instance/"
    ontology_namespace: str = "https://cataforge.dev/ontology/"
    plugins_dir: Path | None = None
    kg_active_doc_types: set[str] = field(default_factory=lambda: set(DEFAULT_KG_ACTIVE_DOC_TYPES))

    def __post_init__(self) -> None:
        if not isinstance(self.db_path, Path):
            self.db_path = Path(self.db_path)
        if self.plugins_dir is not None and not isinstance(self.plugins_dir, Path):
            self.plugins_dir = Path(self.plugins_dir)
        if not isinstance(self.kg_active_doc_types, set):
            self.kg_active_doc_types = set(self.kg_active_doc_types)
