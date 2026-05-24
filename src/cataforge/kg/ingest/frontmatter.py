"""YAML frontmatter → typed triples.

The frontmatter key → predicate table mirrors the JSON-LD context in the
design note §1.7. Each relation key accepts either a single string or a
list of strings; entries are interpreted as CURIEs or item display-IDs,
with display-IDs resolved against the document's own item set first and
the global ``known_item_iris`` map second.

Scalar attribute keys (``status``, ``priority``, ``owner``) emit a single
typed triple. Aliases declared via the legacy ``deps`` field (already
used by :mod:`cataforge.docs.indexer`) are normalised to ``cfa:dependsOn``
so the existing convention keeps working without authors having to rewrite
existing PRDs."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from cataforge.kg.store import Triple

FRONTMATTER_PREDICATE_MAP: dict[str, str] = {
    "realizes":    "cfa:realizes",
    "implements":  "cfa:implements",
    "decomposes":  "cfa:decomposes",
    "validates":   "cfa:validates",
    "conformsTo":  "cfa:conformsTo",
    "mitigates":   "cfa:mitigates",
    "traces":      "cfa:traces",
    "partOf":      "cfa:partOf",
    "dependsOn":   "cfa:dependsOn",
    "deps":        "cfa:dependsOn",
    "references":  "cfa:references",
    "supersedes":  "cfa:supersedes",
    "renders":     "cfa:renders",
    "owner":       "cfa:owner",
    "definedIn":   "cfk:definedIn",
    "replacedBy":  "cfk:replacedBy",
    "cites":       "cfk:cites",
}

_SCALAR_ATTRIBUTE_PREDICATES: dict[str, str] = {
    "status":   "cfa:status",
    "priority": "cfa:priority",
    "label":    "rdfs:label",
}


def _coerce_list(value: object) -> list[str]:
    """Accept ``str`` or ``list[str]``; reject anything else."""
    if value is None:
        return []
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _resolve_target(
    raw: str,
    own_item_iris: dict[str, str],
    known_item_iris: dict[str, str] | None,
) -> str | None:
    """Resolve a raw frontmatter value to an IRI.

    Resolution order:
      1. already a CURIE (``cfa:foo``) or absolute IRI → pass through
      2. matches an item display-ID in the same document → local IRI
      3. matches a display-ID in the cross-document map → that IRI
      4. otherwise drop (return None) — the caller may emit a warning"""
    if not raw:
        return None
    if raw.startswith(("http://", "https://", "urn:")) or (
        ":" in raw and not raw.startswith(":")
    ):
        return raw
    bare_id = raw.split("#", 1)[0]
    if bare_id in own_item_iris:
        return own_item_iris[bare_id]
    if known_item_iris and bare_id in known_item_iris:
        return known_item_iris[bare_id]
    return None


def frontmatter_to_triples(
    subject_iri: str,
    fm: dict[str, Any],
    *,
    own_item_iris: dict[str, str] | None = None,
    known_item_iris: dict[str, str] | None = None,
) -> Iterable[Triple]:
    """Translate a parsed frontmatter dict into Triples for the subject.

    Caller is responsible for having already emitted the subject's
    ``rdf:type`` and ``cfk:hasId`` triples — this function only adds
    relation edges and scalar attributes. Unknown keys are silently
    skipped (callers wanting a stricter validator should run a separate
    pre-flight pass)."""
    own_map = own_item_iris or {}

    for key, predicate in FRONTMATTER_PREDICATE_MAP.items():
        if key not in fm:
            continue
        for raw in _coerce_list(fm[key]):
            target = _resolve_target(raw, own_map, known_item_iris)
            if target is None:
                continue
            yield Triple(s=subject_iri, p=predicate, o=target)

    for key, predicate in _SCALAR_ATTRIBUTE_PREDICATES.items():
        value = fm.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, list | dict):
            continue
        yield Triple(s=subject_iri, p=predicate, o=value)
