"""KG → Markdown rendering subsystem.

Jinja2 environment with KG-aware globals (``kg.query`` / ``sparql`` /
``namespaces``) and a small set of markdown-friendly filters
(``bullet_list`` / ``table`` / ``mermaid_diagram`` / ``link_to``).

Idempotency is a first-class invariant: render-twice on the same store
state must produce byte-identical output (design §4.3, R-03). The
checker module makes that assertion runnable in CI.
"""

from __future__ import annotations

from cataforge.kg.render.checker import (
    IdempotencyCheckResult,
    check_render_idempotent,
)
from cataforge.kg.render.engine import (
    GENERATED_BY_MARKER,
    KGRenderer,
    RenderError,
)
from cataforge.kg.render.filters import (
    bullet_list,
    link_to,
    mermaid_diagram,
    table,
)

__all__ = [
    "GENERATED_BY_MARKER",
    "IdempotencyCheckResult",
    "KGRenderer",
    "RenderError",
    "bullet_list",
    "check_render_idempotent",
    "link_to",
    "mermaid_diagram",
    "table",
]
