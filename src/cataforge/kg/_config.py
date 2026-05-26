"""KG connection configuration (task-5 §5.2).

`KGConfig` is the single configuration object consumed by every entry point in
`cataforge.kg`. Defaults match the spec; the `kg_active_doc_types` default
is the Alpha cutover scope `{prd, arch, test}` per Task 7 §7.1 sub-PR 5
(the README §User decisions Round 2 entry "Default config in this PR
sets `kg_active_doc_types = {"prd", "arch", "test"}` for projects opting
in"). Projects that have not yet ingested into KG remain on the legacy
read path because `cataforge.kg._dispatch.is_active_for()` additionally
gates on `.cataforge/kg/store/` existing on disk.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# The Alpha cutover scope per Task 7 §7.1 + README Round 2. The doctor
# `kg_ingestion_completeness` gate enforces reconciliation for every
# doc_type in this set; per-doc_type rollback (Task 7 §7.5) removes
# entries here. Down-stream projects override via `framework.json`.
DEFAULT_KG_ACTIVE_DOC_TYPES: frozenset[str] = frozenset({"prd", "arch", "test"})


@dataclass
class KGConfig:
    """Configuration for a KnowledgeGraph connection.

    Parameters mirror task-5 §5.2. Only fields actually consumed by sub-PR 2
    code paths (`store_backend`, `db_path`, `governance`, `kg_active_doc_types`)
    are exercised here; the others are declared at full spec width so callers
    that hand a `KGConfig` to later sub-PRs need not be rewritten.
    """

    store_backend: Literal["oxigraph", "memory"] = "oxigraph"
    db_path: Path = field(default_factory=lambda: Path(".cataforge/kg/store"))
    governance: bool = False
    coverage_mode: Literal["strict", "mentions"] = "strict"
    query_timeout: float | None = 30.0
    max_transaction_retries: int = 3
    base_namespace: str = "https://cataforge.dev/instance/"
    ontology_namespace: str = "https://cataforge.dev/ontology/"
    plugins_dir: Path | None = None
    kg_active_doc_types: set[str] = field(
        default_factory=lambda: set(DEFAULT_KG_ACTIVE_DOC_TYPES)
    )

    def __post_init__(self) -> None:
        if not isinstance(self.db_path, Path):
            self.db_path = Path(self.db_path)
        if self.plugins_dir is not None and not isinstance(self.plugins_dir, Path):
            self.plugins_dir = Path(self.plugins_dir)
        if not isinstance(self.kg_active_doc_types, set):
            self.kg_active_doc_types = set(self.kg_active_doc_types)
