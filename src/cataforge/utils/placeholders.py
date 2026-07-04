"""Unresolved-placeholder detection shared across doc gates.

A ``TODO`` / ``TBD`` / ``FIXME`` marks an unfinished spot. It is exempt only
when its own line also carries an ``[ASSUMPTION]`` marker — a tracked, resolved
assumption rather than a loose stub. The per-line scope is deliberate: a global
count would let one ``[ASSUMPTION]`` cancel an unrelated ``TODO`` elsewhere.
"""

from __future__ import annotations

import re

_PLACEHOLDER_RE = re.compile(r"TODO|TBD|FIXME")
_EXEMPT_MARKER = "[ASSUMPTION]"


def count_unresolved_placeholders(text: str) -> int:
    """Count TODO/TBD/FIXME occurrences on lines without an ``[ASSUMPTION]``."""
    total = 0
    for line in text.splitlines():
        if _EXEMPT_MARKER in line:
            continue
        total += len(_PLACEHOLDER_RE.findall(line))
    return total
