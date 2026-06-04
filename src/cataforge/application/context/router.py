"""Fidelity router — dispatch a context operation to the best backend.

For each operation the router considers only the backends the project's
``context.strategy`` enables (``kg-first`` → graph + file; ``doc-only`` →
file only), orders them by their declared fidelity for that operation
(skipping ``UNSUPPORTED``), and consults them highest-first. A backend
that returns ``None`` "cannot serve this request" and the router falls
through to the next; the last backend's result — or raised error — is
authoritative.
"""

from __future__ import annotations

from typing import Any

from cataforge.application.context.backends import DocBackend, KgBackend
from cataforge.application.context.ports import (
    OP_DEPS,
    OP_PLAN_LOAD,
    OP_READ_SECTION,
    Fidelity,
)
from cataforge.domain.kg._dispatch import context_strategy


class FidelityRouter:
    """Routes context operations across an ordered set of backends."""

    def __init__(self, backends: list[Any]) -> None:
        self._backends = backends

    def _ordered(self, op: str) -> list[Any]:
        eligible = [b for b in self._backends if b.fidelity.get(op, Fidelity.UNSUPPORTED)]
        return sorted(eligible, key=lambda b: b.fidelity[op], reverse=True)

    def read_section(
        self, ref: str, project_root: str, *, file_cache: dict[str, list[str]] | None = None
    ) -> str:
        for backend in self._ordered(OP_READ_SECTION):
            result = backend.read_section(ref, project_root, file_cache=file_cache)
            if result is not None:
                return result
        # No backend served it and none raised — surface a not-found error.
        from cataforge.domain.docs.index_ops import SectionNotFoundError

        raise SectionNotFoundError(f"no context backend could resolve {ref!r}")

    def plan_load(
        self, refs: list[str], project_root: str, token_budget: int
    ) -> tuple[list[str], list[str]]:
        for backend in self._ordered(OP_PLAN_LOAD):
            result = backend.plan_load(refs, project_root, token_budget)
            if result is not None:
                return result
        return [], []

    def deps(self, ref: str, project_root: str, max_depth: int) -> list[str]:
        for backend in self._ordered(OP_DEPS):
            result = backend.deps(ref, project_root, max_depth)
            if result is not None:
                return result
        return []


def build_router(project_root: str) -> FidelityRouter:
    """Build a router for ``project_root`` per its ``context.strategy``.

    ``doc-only`` enables the file backend alone; ``kg-first`` (default)
    enables the graph backend ahead of the file backend.
    """
    if context_strategy(project_root) == "doc-only":
        backends: list[Any] = [DocBackend()]
    else:
        backends = [KgBackend(), DocBackend()]
    return FidelityRouter(backends)
