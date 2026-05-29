"""Consumer-side port for the KG read surface ``docs`` depends on.

``docs/loader`` resolves refs through the knowledge graph when a doc_type is
KG-active. To keep the dependency direction one-way (docs depends on an
abstraction it owns, not on the concrete ``cataforge.domain.kg`` package), the read
surface loader consumes is declared here as a structural :class:`Protocol`.
``cataforge.domain.kg.facade.KnowledgeGraph`` satisfies it structurally — no runtime
import of ``kg`` happens here, so this module stays a pure leaf.
"""

from __future__ import annotations

from typing import Any, Protocol


class PlanLoadResult(Protocol):
    """Result of a budgeted plan-load query."""

    ordered: list[str]
    dropped: list[str]


class KGQueryPort(Protocol):
    """The query sub-API loader calls on a connected graph handle."""

    def exists(self, entity_id: str) -> bool: ...

    def entity(self, entity_id: str) -> dict[str, Any] | None: ...

    def depends_on(self, entity_id: str) -> list[str]: ...

    def plan_load(
        self, entity_ids: list[str], token_budget: int, *, include_related: bool
    ) -> PlanLoadResult: ...


class KGReadPort(Protocol):
    """A connected, read-capable knowledge-graph handle.

    Loader only ever reads: it queries via :attr:`query` and renders entity
    bodies from :attr:`store`. Mutation/transaction APIs are intentionally
    absent from the port.
    """

    query: KGQueryPort
    store: Any
