"""Context I/O capability ports + asymmetric fidelity routing.

A small set of capability ports (read / relation) sit in front of the
two context backends — the knowledge graph and the Markdown/file store —
and a :class:`FidelityRouter` dispatches each operation to the
highest-fidelity backend the project's ``context.strategy`` enables.

This lifts the per-call "try KG, else fall back to file" decision that
used to be restated across the loader and the skill prompts into one
operation-level routing point.
"""

from cataforge.domain.context.ports import (
    ContextReadPort,
    Fidelity,
    RelationPort,
)
from cataforge.domain.context.router import FidelityRouter, build_router

__all__ = [
    "ContextReadPort",
    "Fidelity",
    "FidelityRouter",
    "RelationPort",
    "build_router",
]
