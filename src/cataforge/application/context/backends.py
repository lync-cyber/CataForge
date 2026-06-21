"""The two context backends: the knowledge graph and the file/index store.

Each adapts an existing domain read implementation and declares its
per-operation fidelity. Backends never *choose* whether to run — that is
the router's job; they return ``None`` when they cannot serve a request
so the router can fall through to the next-highest-fidelity backend.

Asymmetry is by design: the graph is native for relation closures and
section/entity rendering; the file store is native for byte-level
section slices but only *degraded* for dependency/budget queries (it
relies on the static ``.doc-index.json`` rather than a graph).
"""

from __future__ import annotations

from cataforge.application.context.ports import (
    OP_DEPS,
    OP_PLAN_LOAD,
    OP_READ_SECTION,
    Fidelity,
)
from cataforge.domain.docs import _loader_kg, loader
from cataforge.domain.docs.index_ops import LoadSectionError, parse_ref


class DocBackend:
    """Markdown/file + ``.doc-index.json`` backend (Markdown/file loader primitives)."""

    name = "doc"
    fidelity = {
        OP_READ_SECTION: Fidelity.NATIVE,  # byte-level section slice
        OP_PLAN_LOAD: Fidelity.DEGRADED,  # static est_tokens / flat fallback
        OP_DEPS: Fidelity.DEGRADED,  # static deps[] field, no closure
    }

    def read_section(
        self, ref: str, project_root: str, *, file_cache: dict[str, list[str]] | None = None
    ) -> str | None:
        return loader.extract(ref, project_root, file_cache=file_cache)

    def plan_load(
        self, refs: list[str], project_root: str, token_budget: int
    ) -> tuple[list[str], list[str]] | None:
        return loader.plan_load(refs, project_root, token_budget)

    def deps(self, ref: str, project_root: str, max_depth: int) -> list[str] | None:
        return loader.resolve_deps(ref, project_root, max_depth)


class KgBackend:
    """Knowledge-graph backend (entity render, section narrative, closures)."""

    name = "kg"
    fidelity = {
        OP_READ_SECTION: Fidelity.NATIVE,  # entity render + Section narrative_body
        OP_PLAN_LOAD: Fidelity.NATIVE,  # graph token estimation
        OP_DEPS: Fidelity.NATIVE,  # cf:depends_on transitive closure
    }

    def read_section(
        self, ref: str, project_root: str, *, file_cache: dict[str, list[str]] | None = None
    ) -> str | None:
        try:
            doc_id, section_path, item_id = parse_ref(ref)
        except LoadSectionError:
            return None  # malformed ref — let the file backend raise authoritatively
        return _loader_kg._try_kg_extract(doc_id, section_path, item_id, project_root)

    def plan_load(
        self, refs: list[str], project_root: str, token_budget: int
    ) -> tuple[list[str], list[str]] | None:
        return _loader_kg._try_kg_plan_load(refs, project_root, token_budget)

    def deps(self, ref: str, project_root: str, max_depth: int) -> list[str] | None:
        return _loader_kg._try_kg_resolve_deps(ref, project_root, max_depth)
