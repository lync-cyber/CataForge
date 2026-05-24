"""Prose ID-reference scanner.

Per design §1.8 rule 5: scan only Markdown text nodes for ``[A-Z]+-\\d+``
display IDs; fenced code blocks and inline code must be skipped (otherwise
identifiers like ``R-2D`` inside a hex dump or a Python ``r-2`` token would
generate spurious ``cfa:references`` triples — recorded as R-21 in the
design risk register).

Emits one ``cfa:references`` triple per resolved ID. Unresolved IDs (no
matching ``cfk:hasId`` in the same document's item set) are dropped — the
ingest layer cannot reach into other documents at this stage, so the
caller is expected to do a second pass to confidence-tag cross-doc refs."""

from __future__ import annotations

import re
from collections.abc import Iterable

from markdown_it import MarkdownIt

from cataforge.kg.store import Triple

# Identifiers always have at least one uppercase-letter prefix and a
# hyphen + decimal numeric suffix. The version-string release IDs
# (``v0.5.0``) are not matched here — those are subject IRIs, never
# inline-referenced from prose.
_DISPLAY_ID_RE = re.compile(r"\b([A-Z]+-\d+)\b")

_INLINE_TYPES_TO_SKIP = frozenset({"code_inline"})
_BLOCK_TYPES_TO_SKIP = frozenset({"fence", "code_block"})


def _scan_inline_for_ids(inline_content: str) -> set[str]:
    """Find display IDs in a markdown inline span, skipping backtick-fenced code.

    markdown-it-py keeps inline code as a separate child token, so the
    surrounding inline.content can still legally contain backtick characters
    when authors escape them or use them as literal punctuation. The skip is
    done at the token level (filtering ``code_inline`` children) — this
    helper only needs to scan the raw text after children with code tokens
    have been stripped."""
    return set(_DISPLAY_ID_RE.findall(inline_content))


def scan_prose_refs(
    content: str,
    source_iri: str,
    known_item_iris: dict[str, str],
) -> Iterable[Triple]:
    """Yield ``cfa:references`` triples for resolved display IDs in prose.

    Parameters
    ----------
    content : str
        Raw Markdown body (frontmatter already stripped).
    source_iri : str
        IRI to use as the triple subject for unattributed references in the
        body — typically the document IRI. Section-scoped subjects (per
        item-heading) are out of scope for this first pass.
    known_item_iris : dict[str, str]
        Map of display-ID → IRI for items declared *inside* this document.
        Cross-doc resolution happens later, when the migrator assembles all
        known item IRIs from every ingested file.
    """
    parser = MarkdownIt("commonmark")
    tokens = parser.parse(content)

    found_ids: set[str] = set()
    for tok in tokens:
        if tok.type in _BLOCK_TYPES_TO_SKIP:
            continue
        if tok.type != "inline" or not tok.children:
            continue
        for child in tok.children:
            if child.type in _INLINE_TYPES_TO_SKIP:
                continue
            if not child.content:
                continue
            found_ids.update(_scan_inline_for_ids(child.content))

    for display_id in sorted(found_ids):
        target = known_item_iris.get(display_id)
        if target is None or target == source_iri:
            continue
        yield Triple(s=source_iri, p="cfa:references", o=target)
