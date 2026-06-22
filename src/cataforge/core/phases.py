"""SDLC phase ↔ doc_type vocabulary.

Pure framework constants: the recognised phase names, each gated phase's
primary doc_type(s), and the doc_type → phase inverse. No dependencies, so any
layer may import it downward — the application phase service and the runtime
skill runner both resolve a doc_type's owning phase through here.
"""

from __future__ import annotations

# Recognised 当前阶段 values across all execution modes — the union of the
# standard 7-phase sequence with the agile merged phases (``planning`` for
# agile-lite, fusing requirements+architecture; ``brief`` for agile-prototype,
# fusing Phase 1–4). Membership is a recognition gate; ordering carries no
# semantics.
PHASES: tuple[str, ...] = (
    "brief",
    "planning",
    "requirements",
    "architecture",
    "ui_design",
    "dev_planning",
    "development",
    "testing",
    "deployment",
    "completed",
)

# Each gated phase's expected primary document(s) (base doc_type; the ``-lite``
# variant is accepted under agile modes). A tuple gates on every listed
# doc_type. Phases absent here carry no document gate (development is code-only;
# completed is terminal). The agile merged ``planning`` phase fuses
# requirements+architecture, so it gates on both prd and arch; ``brief``
# produces the single agile-prototype doc.
PHASE_DOC_TYPE: dict[str, str | tuple[str, ...]] = {
    "brief": "brief",
    "planning": ("prd", "arch"),
    "requirements": "prd",
    "architecture": "arch",
    "ui_design": "ui-spec",
    "dev_planning": "dev-plan",
    "testing": "test-report",
    "deployment": "deploy-spec",
}

# Agile-merged phases gate on multiple doc_types (``planning`` fuses
# requirements+architecture). They are excluded from the doc_type→phase
# inverse so each base doc_type resolves to its single standard phase.
_MERGED_PHASES = frozenset({"planning"})


def phase_for_doc_type(doc_type: str) -> str | None:
    """Return the standard lifecycle phase that owns *doc_type*, or None.

    Inverse of :data:`PHASE_DOC_TYPE`. Used to attribute a review run to the
    reviewed artifact's phase instead of the instruction file's (possibly
    stale) 当前阶段. The ``-lite`` suffix resolves to its base doc_type.
    """
    base = doc_type[:-5] if doc_type.endswith("-lite") else doc_type
    for phase, dts in PHASE_DOC_TYPE.items():
        if phase in _MERGED_PHASES:
            continue
        types = (dts,) if isinstance(dts, str) else dts
        if base in types:
            return phase
    return None
