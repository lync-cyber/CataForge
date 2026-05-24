"""Project-level migration helpers (NAV, review frontmatter, KG cutover).

Lives under :mod:`cataforge.core.migrate` instead of :mod:`cataforge.docs`
because these helpers fix *project state* (legacy file shapes, missing
frontmatter) — they are not part of the legacy doc-index machinery that
:mod:`cataforge.kg` supersedes."""

from __future__ import annotations

__all__: list[str] = []
