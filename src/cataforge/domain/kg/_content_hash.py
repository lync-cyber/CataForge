"""Canonical content-hash for entity idempotency.

The single hash function both authoring paths (`context write` /
`kg add`) use to derive an entity's `cf:content_hash`. Content-sensitive:
the digest changes when the title or any slot value changes, so a
re-write of identical content is a no-op and a changed value replaces
the entity's quads atomically.
"""

from __future__ import annotations

import hashlib

_UNIT_SEP = "\x1f"


def entity_content_hash(title: str, slots: dict[str, str] | None = None) -> str:
    """Return the canonical content hash for ``(title, slots)``.

    Slots are sorted by key so the digest is order-independent.
    """
    slot_digest = _UNIT_SEP.join(f"{k}={v}" for k, v in sorted((slots or {}).items()))
    payload = f"{title}{_UNIT_SEP}{slot_digest}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = ["entity_content_hash"]
