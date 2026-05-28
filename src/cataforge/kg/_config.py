"""KG connection configuration.

`KGConfig` is the single configuration object consumed by every entry point in
`cataforge.kg`. The `kg_active_doc_types` default is `{prd, arch, test}`.
Projects that have not yet ingested into KG remain on the legacy read path
because `cataforge.kg._dispatch.is_active_for()` additionally gates on
`.cataforge/kg/store/` existing on disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# Default active doc_types. The doctor `kg_ingestion_completeness` gate
# enforces reconciliation for every doc_type in this set. Down-stream
# projects override via `framework.json`.
#
# Expansion path (per task-7 rollout strategy §7.5):
#   0.5.x  (current) — prd + arch + test
#   0.6.0  candidate — add `dev-plan` (T-NNN, depends_on graph),
#                      add `ui-spec` (C-NNN / P-NNN)
# Ingest already supports T/C/P prefixes via `ENTITY_PREFIX_TO_CLASS`;
# expansion requires (a) extending the fixture vertical-slice to cover the
# new doc_type, (b) regression on golden-file diff, (c) updating this
# constant + scaffold framework.json default. Project owners can opt in
# earlier by editing their own `framework.json.kg.kg_active_doc_types`.
DEFAULT_KG_ACTIVE_DOC_TYPES: frozenset[str] = frozenset({"prd", "arch", "test"})


@dataclass
class KGConfig:
    """Configuration for a KnowledgeGraph connection."""

    store_backend: Literal["oxigraph", "memory"] = "oxigraph"
    db_path: Path = field(default_factory=lambda: Path(".cataforge/kg/store"))
    governance: bool = False
    coverage_mode: Literal["strict", "mentions"] = "strict"
    query_timeout: float | None = 30.0
    max_transaction_retries: int = 3
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
