"""Check registry — the single source ``CHECKS_MANIFEST`` is derived from.

Every Layer 1 check registers a :class:`CheckSpec` at import time (see the
``checks`` package). The manifest consumed by framework-review B3 is a
read-only projection of this registry, so "manifest ↔ implementation drift"
is impossible by construction. Hand-written manifest entries are forbidden.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.findings import Finding

# COMMON-RULES §统一问题分类体系 (14) plus the two code-review SKILL.md
# Layer 2 dimensions that have Layer 1 counterparts.
CATEGORIES = frozenset(
    {
        "completeness",
        "consistency",
        "convention",
        "security",
        "feasibility",
        "ambiguity",
        "structure",
        "error-handling",
        "performance",
        "test-quality",
        "duplication",
        "dead-code",
        "complexity",
        "coupling",
        "integration-wiring",
        "visual-fidelity",
    }
)

MANIFEST_SEVERITIES = frozenset({"fail-on-error", "warn", "informational"})
MODES = frozenset({"review", "scan"})


@dataclass(frozen=True)
class CheckSpec:
    """One registered Layer 1 check.

    ``severity`` is the manifest-level gate class (individual findings carry
    their own fail/warn/info severity); ``modes`` declares where it runs.
    In scan mode, ``informational`` checks are the only ones ``--focus``
    filters — gating checks always run.
    """

    id: str
    title: str
    severity: str
    category: str
    modes: frozenset[str]
    run: Callable[[CheckContext], list[Finding]]


REGISTRY: list[CheckSpec] = []


def register_check(spec: CheckSpec) -> CheckSpec:
    if any(existing.id == spec.id for existing in REGISTRY):
        raise ValueError(f"duplicate check id: {spec.id}")
    if spec.severity not in MANIFEST_SEVERITIES:
        raise ValueError(f"{spec.id}: invalid severity {spec.severity!r}")
    if spec.category not in CATEGORIES:
        raise ValueError(f"{spec.id}: invalid category {spec.category!r}")
    if not spec.modes or not spec.modes <= MODES:
        raise ValueError(f"{spec.id}: invalid modes {sorted(spec.modes)!r}")
    REGISTRY.append(spec)
    return spec


_SEVERITY_RANK = {"fail-on-error": 0, "warn": 1, "informational": 2}


def checks_for_mode(mode: str) -> list[CheckSpec]:
    """Checks for *mode*, gating first (cheap surface defects surface before
    slow informational probes); stable within a gate class."""
    return sorted(
        (c for c in REGISTRY if mode in c.modes),
        key=lambda c: _SEVERITY_RANK[c.severity],
    )


def derive_manifest() -> tuple[dict[str, str], ...]:
    """Read-only manifest projection consumed by framework-review B3."""
    return tuple(
        {
            "id": spec.id,
            "title": spec.title,
            "severity": spec.severity,
            "modes": "+".join(sorted(spec.modes)),
        }
        for spec in REGISTRY
    )
