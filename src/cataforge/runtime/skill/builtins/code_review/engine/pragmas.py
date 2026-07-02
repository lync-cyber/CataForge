"""Unified exemption pragma — the single escape-hatch grammar for Layer 1.

Grammar (one per comment line, any comment style):

    cataforge: allow(<check-id>, reason="<非空理由>")

``<check-id>`` is a manifest check id, full (``code_review.ui_fidelity``)
or specifier-only (``ui_fidelity``). ``reason`` is required by policy: an
allowance without one still suppresses the check (progressive adoption)
but the consuming check emits a WARN finding so exemption sprawl stays
visible. Full grammar reference: ``.cataforge/references/pragma-grammar.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ALLOW_RE = re.compile(
    r"cataforge:\s*allow\(\s*([A-Za-z0-9_.-]+)\s*(?:,\s*reason\s*=\s*\"([^\"]*)\"\s*)?\)"
)


@dataclass(frozen=True)
class Allowance:
    """One parsed ``allow(...)`` pragma occurrence."""

    check: str
    reason: str
    line: int


def parse_allowances(text: str) -> tuple[Allowance, ...]:
    out: list[Allowance] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _ALLOW_RE.finditer(line):
            out.append(Allowance(check=match.group(1), reason=match.group(2) or "", line=lineno))
    return tuple(out)


def file_allowance(text: str, check_id: str) -> Allowance | None:
    """First allowance matching *check_id* (full id or bare specifier)."""
    specifier = check_id.rsplit(".", 1)[-1]
    for allowance in parse_allowances(text):
        if allowance.check in (check_id, specifier):
            return allowance
    return None
