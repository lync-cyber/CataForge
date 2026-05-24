"""Triple-stream canonicalisation — guarantees ingest idempotence.

Re-ingesting an unchanged file must produce the same triple set (modulo
ordering); re-ingesting after a whitespace-only edit must also produce the
same set. ``canonicalize`` is the choke-point that enforces both: it
deduplicates, strips leading/trailing whitespace inside string literals,
collapses internal runs of whitespace, and returns a list sorted on the
``(s, p, o)`` key so downstream diffing is deterministic.

Numeric and boolean literals are passed through untouched — only ``str``
objects are normalised."""

from __future__ import annotations

import re
from collections.abc import Iterable

from cataforge.kg.store import Triple

_WHITESPACE_RUN = re.compile(r"\s+")


def _normalise_literal(value: str | int | float | bool) -> str | int | float | bool:
    if not isinstance(value, str):
        return value
    # Strip outer whitespace, collapse interior runs to a single space.
    return _WHITESPACE_RUN.sub(" ", value.strip())


def canonicalize(triples: Iterable[Triple]) -> list[Triple]:
    """Deduplicate, normalise string literals, and sort the triple stream.

    Sort key is ``(s, p, str(o))`` so triples that share the same subject
    and predicate but differ only by object value stay grouped. Returns a
    fresh list — never mutates the input."""
    seen: dict[tuple[str, str, str | int | float | bool], Triple] = {}
    for t in triples:
        normalised = Triple(
            s=t.s.strip(),
            p=t.p.strip(),
            o=_normalise_literal(t.o),
        )
        key = (normalised.s, normalised.p, normalised.o)
        if key not in seen:
            seen[key] = normalised
    return sorted(seen.values(), key=lambda t: (t.s, t.p, str(t.o)))
