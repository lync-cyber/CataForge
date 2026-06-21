"""Routed context-read facade (application layer).

Wraps the :class:`FidelityRouter` so callers get strategy-aware reads
without knowing which backend served them. The Markdown/file primitives live
in ``domain.docs.loader``; here they are composed with the graph backend.
CLI argument parsing and output formatting live in the interface layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cataforge.application.context.router import build_router
from cataforge.domain.docs.index_ops import LoadSectionError


def extract(ref: str, project_root: str, file_cache: dict[str, Any] | None = None) -> str:
    """Strategy-routed read of a single ``doc_id#§N[.item]`` reference."""
    return build_router(project_root).read_section(ref, project_root, file_cache=file_cache)


def extract_batch(
    refs: list[str], project_root: str
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    successes: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    file_cache: dict[str, list[str]] = {}
    router = build_router(project_root)
    for ref in refs:
        try:
            successes.append((ref, router.read_section(ref, project_root, file_cache=file_cache)))
        except LoadSectionError as e:
            errors.append((ref, str(e)))
    return successes, errors


def plan_load(refs: list[str], project_root: str, token_budget: int) -> tuple[list[str], list[str]]:
    return build_router(project_root).plan_load(refs, project_root, token_budget)


def resolve_deps(ref: str, project_root: str, max_depth: int = 2) -> list[str]:
    return build_router(project_root).deps(ref, project_root, max_depth)


@dataclass
class LoadResult:
    """Structured outcome of a section load — no I/O, formatting is the caller's job."""

    successes: list[tuple[str, str]] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    dep_refs: list[str] = field(default_factory=list)


def load_sections(
    refs: list[str],
    project_root: str,
    *,
    with_deps: bool = False,
    budget: int | None = None,
) -> LoadResult:
    """Resolve dependency expansion + token budget, then batch-read.

    Pure: returns the data the CLI formats. ``dep_refs`` are the extra refs
    auto-added by ``with_deps``; ``deferred`` are refs dropped for budget.
    """
    working: list[str] = list(refs)
    dep_refs: list[str] = []

    if with_deps:
        seen = set(working)
        for ref in list(working):
            for dep in resolve_deps(ref, project_root):
                if dep not in seen:
                    seen.add(dep)
                    dep_refs.append(dep)
        working.extend(dep_refs)

    deferred: list[str] = []
    if budget is not None:
        working, deferred = plan_load(working, project_root, budget)

    successes, errors = extract_batch(working, project_root)
    return LoadResult(successes=successes, errors=errors, deferred=deferred, dep_refs=dep_refs)
