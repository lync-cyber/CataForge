"""KG connection configuration (task-5 §5.2).

`KGConfig` is the single configuration object consumed by every entry point in
`cataforge.kg`. Defaults match the spec; round-2 decision: `kg_active_doc_types`
defaults to an empty set so legacy `loader.extract()` is the read path for
every doc_type until Alpha cutover (sub-PR 5) populates it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


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
    kg_active_doc_types: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not isinstance(self.db_path, Path):
            self.db_path = Path(self.db_path)
        if self.plugins_dir is not None and not isinstance(self.plugins_dir, Path):
            self.plugins_dir = Path(self.plugins_dir)
        if not isinstance(self.kg_active_doc_types, set):
            self.kg_active_doc_types = set(self.kg_active_doc_types)
