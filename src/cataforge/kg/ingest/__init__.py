"""Markdown → KG triples ingest pipeline.

Four-stage flow that the top-level :func:`ingest_markdown` orchestrates:

1. parse YAML frontmatter + markdown headings (:mod:`.markdown`)
2. map frontmatter relation keys to typed edges (:mod:`.frontmatter`)
3. scan prose for ``[A-Z]+-\\d+`` ID refs, skipping code (:mod:`.prose_refs`)
4. canonicalise the triple stream so re-ingest is byte-stable (:mod:`.canonical`)

Display-ID prefix → concrete artifact class table lives in :data:`ID_PREFIX_MAP`
(matches ``docs/research/kg-feature-upgrade-design.md`` §1.8). Frontmatter
key → predicate table lives in :data:`FRONTMATTER_PREDICATE_MAP` (matches
the §1.7 JSON-LD context).
"""

from __future__ import annotations

from cataforge.kg.ingest.canonical import canonicalize
from cataforge.kg.ingest.frontmatter import (
    FRONTMATTER_PREDICATE_MAP,
    frontmatter_to_triples,
)
from cataforge.kg.ingest.markdown import (
    ID_PREFIX_MAP,
    DocumentNode,
    IngestResult,
    ItemNode,
    ingest_markdown,
)
from cataforge.kg.ingest.prose_refs import scan_prose_refs

__all__ = [
    "FRONTMATTER_PREDICATE_MAP",
    "ID_PREFIX_MAP",
    "DocumentNode",
    "IngestResult",
    "ItemNode",
    "canonicalize",
    "frontmatter_to_triples",
    "ingest_markdown",
    "scan_prose_refs",
]
