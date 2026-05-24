"""Render-twice idempotency checker.

Two renderings of the same template against the same store state must
produce byte-identical output (design §4.3 / risk R-03). This module is
the single entry point for that assertion — used by tests and by the
``cataforge kg render --check`` CLI flag.

When a divergence is detected, the result carries both renderings so the
caller can produce a unified diff for the user."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cataforge.kg.render.engine import KGRenderer


@dataclass(frozen=True)
class IdempotencyCheckResult:
    """Outcome of a single render-twice check."""

    template_name: str
    is_idempotent: bool
    first: str = ""
    second: str = ""

    @property
    def diff_preview(self) -> str:
        """First differing line of the two renderings (for short-form reports)."""
        for i, (a, b) in enumerate(zip(
            self.first.splitlines(), self.second.splitlines(), strict=False,
        )):
            if a != b:
                return f"line {i + 1}: {a!r} vs {b!r}"
        if len(self.first) != len(self.second):
            return f"length differs: {len(self.first)} vs {len(self.second)} chars"
        return ""


def check_render_idempotent(
    renderer: KGRenderer,
    template_name: str,
    **context: Any,
) -> IdempotencyCheckResult:
    """Render *template_name* twice and compare byte-for-byte."""
    a = renderer.render(template_name, **context)
    b = renderer.render(template_name, **context)
    return IdempotencyCheckResult(
        template_name=template_name,
        is_idempotent=(a == b),
        first=a,
        second=b,
    )
