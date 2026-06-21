"""Context I/O capability ports + asymmetric fidelity routing (application layer).

A small set of capability ports (read / relation) sit in front of the
two context backends — the knowledge graph and the Markdown/file store —
and a :class:`FidelityRouter` dispatches each operation to the
highest-fidelity backend the project's ``context.mode`` enables.

This lifts the per-call "try KG, else fall back to file" decision that
used to be restated across the loader and the skill prompts into one
operation-level routing point in the application layer.
"""

from cataforge.application.context.ports import (
    ContextReadPort,
    Fidelity,
    RelationPort,
)
from cataforge.application.context.read import (
    extract,
    extract_batch,
    plan_load,
    resolve_deps,
)
from cataforge.application.context.router import FidelityRouter, build_router
from cataforge.application.context.write import (
    ContextModeError,
    DocIndexResult,
    DocValidationReport,
    author_entity,
    finalize,
    ingest,
    reconcile_check,
    write_narrative,
)

__all__ = [
    "ContextModeError",
    "ContextReadPort",
    "DocIndexResult",
    "DocValidationReport",
    "Fidelity",
    "FidelityRouter",
    "RelationPort",
    "author_entity",
    "build_router",
    "extract",
    "extract_batch",
    "finalize",
    "ingest",
    "plan_load",
    "reconcile_check",
    "resolve_deps",
    "write_narrative",
]
