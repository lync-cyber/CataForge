"""The two context backends: the knowledge graph and the file/index store.

Each wraps the existing read implementations and declares its
per-operation fidelity. Backends never *choose* whether to run — that is
the router's job; they return ``None`` when they cannot serve a request
so the router can fall through to the next-highest-fidelity backend.

Asymmetry is by design: the graph is native for relation closures and
section/entity rendering; the file store is native for byte-level
section slices but only *degraded* for dependency/budget queries (it
relies on the static ``.doc-index.json`` rather than a graph).
"""

from __future__ import annotations

from typing import Any

from cataforge.domain.context.ports import (
    OP_DEPS,
    OP_PLAN_LOAD,
    OP_READ_SECTION,
    Fidelity,
)


class DocBackend:
    """Markdown/file + ``.doc-index.json`` backend."""

    name = "doc"
    fidelity = {
        OP_READ_SECTION: Fidelity.NATIVE,  # byte-level section slice
        OP_PLAN_LOAD: Fidelity.DEGRADED,  # static est_tokens / flat fallback
        OP_DEPS: Fidelity.DEGRADED,  # static deps[] field, no closure
    }

    def read_section(
        self, ref: str, project_root: str, *, file_cache: dict[str, Any] | None = None
    ) -> str | None:
        from cataforge.domain.docs.loader import _doc_extract

        return _doc_extract(ref, project_root, file_cache=file_cache)

    def plan_load(
        self, refs: list[str], project_root: str, token_budget: int
    ) -> tuple[list[str], list[str]] | None:
        from cataforge.domain.docs.loader import _doc_plan_load

        return _doc_plan_load(refs, project_root, token_budget)

    def deps(self, ref: str, project_root: str, max_depth: int) -> list[str] | None:
        from cataforge.domain.docs.loader import _doc_resolve_deps

        return _doc_resolve_deps(ref, project_root, max_depth)


class KgBackend:
    """Knowledge-graph backend (entity render, section narrative, closures)."""

    name = "kg"
    fidelity = {
        OP_READ_SECTION: Fidelity.NATIVE,  # entity render + Section narrative_body
        OP_PLAN_LOAD: Fidelity.NATIVE,  # graph token estimation
        OP_DEPS: Fidelity.NATIVE,  # cf:depends_on transitive closure
    }

    def read_section(
        self, ref: str, project_root: str, *, file_cache: dict[str, Any] | None = None
    ) -> str | None:
        from cataforge.domain.docs._loader_kg import _try_kg_extract
        from cataforge.domain.docs.index_ops import LoadSectionError, parse_ref

        try:
            doc_id, section_path, item_id = parse_ref(ref)
        except LoadSectionError:
            return None  # malformed ref — let the file backend raise authoritatively
        return _try_kg_extract(doc_id, section_path, item_id, project_root)

    def plan_load(
        self, refs: list[str], project_root: str, token_budget: int
    ) -> tuple[list[str], list[str]] | None:
        from cataforge.domain.docs._loader_kg import _try_kg_plan_load

        return _try_kg_plan_load(refs, project_root, token_budget)

    def deps(self, ref: str, project_root: str, max_depth: int) -> list[str] | None:
        from cataforge.domain.docs._loader_kg import _try_kg_resolve_deps

        return _try_kg_resolve_deps(ref, project_root, max_depth)
