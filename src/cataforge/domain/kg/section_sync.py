"""Cascade-consistent narrative authoring over the Section tile-cover.

Ingest stores each heading (level >= 2) as its own Section node while every
level-2 node's ``narrative_body`` embeds its subsections verbatim — and the
whole-document export concatenates exactly those level-2 tiles. A narrative
write at any depth therefore has to land in one level-2 tile AND in every
section node whose text that tile embeds, or the two copies diverge:
sub-section writes never reach the export while tile writes leave stale
sub-section nodes behind.

:class:`CascadeWriter` closes that gap. Each write is resolved onto its
enclosing level-2 tile, the tile body is patched at the target heading's
span, and the patched tile is re-sliced with the same heading parser ingest
uses (:func:`~cataforge.domain.kg.ingest.scan.heading_spans`) so slicing
semantics live in exactly one place. ``flush()`` stages one consistent
upsert/delete set into the enclosing transaction; a target that cannot be
located raises instead of writing an unexportable node.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from cataforge.domain.kg._errors import KGEntityNotFoundError, KGValidationError
from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _strv,
    cf_namespace,
    escape_sparql_literal,
    select_rows,
)
from cataforge.domain.kg.ingest.scan import heading_spans

if TYPE_CHECKING:
    from cataforge.domain.kg.transaction import TransactionContext

_HEADING_RE = re.compile(r"^(#{2,6})\s+(.*\S)\s*$")


def normalize_narrative(
    narrative: str, anchor: str, *, existing_level: int | None
) -> tuple[str, int]:
    """Return ``(narrative_body, level)`` with a leading heading guaranteed.

    The export pipeline concatenates each Section's ``narrative_body``
    verbatim, so the body must carry its own heading line. If the first
    non-blank line is a level-2..6 heading, its text must equal ``anchor``
    (a mismatch produces ghost/missing sections on export) and its depth
    sets the level. Otherwise a ``{'#' * level} {anchor}`` line is prepended,
    with ``level`` taken from the existing section (default 2).
    """
    lines = narrative.split("\n")
    first_idx = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if first_idx is not None:
        m = _HEADING_RE.match(lines[first_idx])
        if m is not None:
            heading_text = m.group(2).strip()
            if heading_text != anchor:
                raise KGValidationError(
                    f"section heading {heading_text!r} does not match anchor {anchor!r}; "
                    "a heading/anchor mismatch produces a ghost or missing section on export — "
                    "make the first heading line read exactly the anchor text."
                )
            return narrative, len(m.group(1))
    level = existing_level if existing_level is not None else 2
    return f"{'#' * level} {anchor}\n{narrative}", level


@dataclass(frozen=True)
class _StoredSection:
    anchor: str
    level: int
    position: int


def desynced_tile_sections(store: Any, config: Any, doc_iri: str) -> list[str]:
    """Anchors whose Section node body disagrees with its level-2 tile.

    Tile-cover invariant: every level-2 Section's ``narrative_body`` embeds
    its subsections verbatim. A write that updated only one copy leaves the
    graph internally inconsistent — the export renders the tile while
    section-level reads serve the node, so revisions can silently diverge.
    Returns the offending anchors: nodes whose body differs from the slice
    their tile embeds, plus nodes no tile slices out at all (unexportable).
    """
    from cataforge.domain.kg._sparql_utils import assert_safe_iri  # noqa: PLC0415

    ns = cf_namespace(config)
    safe = assert_safe_iri(doc_iri)
    sparql = (
        f"PREFIX cf: <{ns}> "
        "SELECT ?anchor ?level ?body WHERE { "
        f"?s a cf:Section ; cf:part_of_document <{safe}> ; "
        "cf:section_anchor ?anchor ; cf:narrative_body ?body . "
        "OPTIONAL { ?s cf:section_level ?level } }"
    )
    nodes: dict[str, tuple[int, str]] = {}
    for row in select_rows(store, sparql):
        anchor = _strv(_row_lookup(row, "anchor"))
        body = _strv(_row_lookup(row, "body"))
        if anchor is None or body is None:
            continue
        level = _strv(_row_lookup(row, "level"))
        nodes[anchor] = (int(level) if level is not None else 2, body)

    expected: dict[str, str] = {}
    for tile_level, tile_body in nodes.values():
        if tile_level != 2:
            continue
        tile_lines = _trim_trailing_blanks(tile_body.split("\n"))
        tile_text = "\n".join(tile_lines)
        for span in heading_spans(tile_text, 0)[1:]:
            child = span.title.strip()
            if child and child not in expected:
                expected[child] = "\n".join(
                    _trim_trailing_blanks(tile_lines[span.line_start : span.line_end])
                )

    desynced = {
        anchor
        for anchor, (level, body) in nodes.items()
        if level != 2 and expected.get(anchor) != body
    }
    return sorted(desynced)


@dataclass
class _PlannedSection:
    body: str
    level: int
    explicit_contains: list[str] | None = None


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _trim_trailing_blanks(lines: list[str]) -> list[str]:
    out = list(lines)
    while out and not out[-1].strip():
        out.pop()
    return out


class CascadeWriter:
    """Plan cascade-consistent Section writes, then stage them in one flush.

    All writes of one logical operation (a single ``write-narrative`` call or
    one ``transact`` batch) go through the same instance so later writes see
    earlier planned tile bodies instead of the stale store state, and every
    anchor is staged at most once.
    """

    def __init__(self, txn: TransactionContext) -> None:
        self._txn = txn
        self._ns = cf_namespace(txn.config)
        self._planned: dict[tuple[str, str], _PlannedSection] = {}
        self._deletes: set[tuple[str, str]] = set()
        self._tile_of: dict[tuple[str, str], str] = {}

    # -- public --------------------------------------------------------------

    def write(
        self,
        *,
        doc_id: str,
        anchor: str,
        narrative: str,
        contained_entity_ids: list[str] | None = None,
    ) -> None:
        """Plan one narrative write, cascading through its level-2 tile."""
        stored = self._stored_sections(doc_id)
        key = (doc_id, anchor)
        planned = self._planned.get(key)
        existing_level = (
            planned.level
            if planned is not None
            else stored[anchor].level
            if anchor in stored
            else None
        )
        body, level = normalize_narrative(narrative, anchor, existing_level=existing_level)

        if existing_level is None:
            if level != 2:
                raise KGValidationError(
                    f"anchor {anchor!r} does not exist in document {doc_id!r} and its "
                    f"heading is level {level}; a new sub-section has no level-2 tile to "
                    "land in and would never reach the export. Revise the enclosing "
                    "level-2 section with the sub-section embedded in its body instead."
                )
            self._plan_tile(doc_id, anchor, body, stored, contained_entity_ids)
            return

        if existing_level == 2:
            self._plan_tile(doc_id, anchor, body, stored, contained_entity_ids)
            return

        tile_anchor = self._enclosing_tile(doc_id, anchor, stored)
        tile_body = self._current_tile_body(doc_id, tile_anchor)
        patched = self._patch_tile(tile_body, anchor, body, doc_id=doc_id, tile=tile_anchor)
        self._plan_tile(doc_id, tile_anchor, patched, stored, None)
        target_plan = self._planned.get(key)
        if target_plan is None:
            raise KGValidationError(
                f"patched tile {tile_anchor!r} no longer slices out anchor {anchor!r} "
                f"in document {doc_id!r} — the write cannot be represented consistently."
            )
        if contained_entity_ids is not None:
            target_plan.explicit_contains = list(contained_entity_ids)

    def flush(self) -> int:
        """Stage the planned deletes and upserts; return the upsert count."""
        for doc_id, anchor in sorted(self._deletes - set(self._planned)):
            try:
                self._txn.delete_entity(f"doc/{doc_id}/sec/{anchor}", cascade=True)
            except KGEntityNotFoundError:
                continue
        for (doc_id, anchor), plan in self._planned.items():
            contains = (
                plan.explicit_contains
                if plan.explicit_contains is not None
                else self._stored_contains(doc_id, anchor)
            )
            self._txn.add_section(
                doc_id,
                anchor,
                plan.body,
                _sha256(plan.body),
                level=plan.level,
                title=anchor,
                contained_entity_ids=contains,
            )
        return len(self._planned)

    # -- planning ------------------------------------------------------------

    def _plan_tile(
        self,
        doc_id: str,
        tile_anchor: str,
        tile_body: str,
        stored: dict[str, _StoredSection],
        explicit_contains: list[str] | None,
    ) -> None:
        """Plan the tile upsert plus the re-sliced sub-section upserts/deletes."""
        tile_lines = _trim_trailing_blanks(tile_body.split("\n"))
        tile_text = "\n".join(tile_lines)
        spans = heading_spans(tile_text, 0)
        tile_key = (doc_id, tile_anchor)
        prior_children = {
            k for k, t in self._tile_of.items() if k[0] == doc_id and t == tile_anchor
        }

        new_children: dict[str, _PlannedSection] = {}
        for span in spans[1:] if spans else []:
            child_anchor = span.title.strip()
            if not child_anchor or child_anchor == tile_anchor or child_anchor in new_children:
                continue
            existing = stored.get(child_anchor)
            if existing is not None and not self._within_tile(existing, tile_anchor, stored):
                continue  # first-wins: the anchor belongs to another tile's subtree
            child_lines = _trim_trailing_blanks(tile_lines[span.line_start : span.line_end])
            new_children[child_anchor] = _PlannedSection(
                body="\n".join(child_lines), level=span.level
            )

        stored_members = {
            row.anchor
            for row in stored.values()
            if row.anchor != tile_anchor and self._within_tile(row, tile_anchor, stored)
        }
        removed = (stored_members | {k[1] for k in prior_children}) - set(new_children)
        for anchor in removed:
            child_key = (doc_id, anchor)
            self._deletes.add(child_key)
            self._planned.pop(child_key, None)
            self._tile_of.pop(child_key, None)

        tile_level = self._planned[tile_key].level if tile_key in self._planned else 2
        self._planned[tile_key] = _PlannedSection(
            body=tile_text, level=tile_level, explicit_contains=explicit_contains
        )
        self._deletes.discard(tile_key)
        for child_anchor, plan in new_children.items():
            child_key = (doc_id, child_anchor)
            prior = self._planned.get(child_key)
            if prior is not None and prior.explicit_contains is not None:
                plan.explicit_contains = prior.explicit_contains
            self._planned[child_key] = plan
            self._tile_of[child_key] = tile_anchor
            self._deletes.discard(child_key)

    def _patch_tile(
        self, tile_body: str, anchor: str, new_body: str, *, doc_id: str, tile: str
    ) -> str:
        """Replace ``anchor``'s heading span inside ``tile_body`` with ``new_body``."""
        lines = tile_body.split("\n")
        spans = heading_spans(tile_body, 0)
        target = next((s for s in spans[1:] if s.title.strip() == anchor), None)
        if target is None:
            raise KGValidationError(
                f"section {anchor!r} is not embedded in its level-2 tile {tile!r} of "
                f"document {doc_id!r}; the graph copies have diverged — re-ingest the "
                "document (`cataforge context ingest`) to restore consistency."
            )
        replacement = _trim_trailing_blanks(new_body.split("\n"))
        if target.line_end < len(lines):
            replacement.append("")
        return "\n".join(lines[: target.line_start] + replacement + lines[target.line_end :])

    def _enclosing_tile(self, doc_id: str, anchor: str, stored: dict[str, _StoredSection]) -> str:
        key = (doc_id, anchor)
        if key in self._tile_of:
            return self._tile_of[key]
        target = stored.get(anchor)
        tile = None
        if target is not None:
            tiles = [r for r in stored.values() if r.level == 2 and r.position <= target.position]
            tile = max(tiles, key=lambda r: r.position, default=None)
        if tile is None:
            raise KGValidationError(
                f"section {anchor!r} in document {doc_id!r} has no enclosing level-2 "
                "tile; re-ingest the document (`cataforge context ingest`) to restore "
                "its structure."
            )
        return tile.anchor

    def _within_tile(
        self, row: _StoredSection, tile_anchor: str, stored: dict[str, _StoredSection]
    ) -> bool:
        tile = stored.get(tile_anchor)
        if tile is None:
            return False
        next_tiles = [
            r.position for r in stored.values() if r.level == 2 and r.position > tile.position
        ]
        upper = min(next_tiles, default=None)
        return row.position > tile.position and (upper is None or row.position < upper)

    # -- store reads (pre-transaction state) ----------------------------------

    def _stored_sections(self, doc_id: str) -> dict[str, _StoredSection]:
        safe = escape_sparql_literal(doc_id)
        sparql = (
            f"PREFIX cf: <{self._ns}> "
            "SELECT ?anchor ?level ?position WHERE { "
            f'?s a cf:Section ; cf:source_doc "{safe}" ; cf:section_anchor ?anchor . '
            "OPTIONAL { ?s cf:section_level ?level } "
            "OPTIONAL { ?s cf:position ?position } }"
        )
        out: dict[str, _StoredSection] = {}
        for row in select_rows(self._txn.store, sparql):
            anchor = _strv(_row_lookup(row, "anchor"))
            if anchor is None:
                continue
            level = _strv(_row_lookup(row, "level"))
            position = _strv(_row_lookup(row, "position"))
            out[anchor] = _StoredSection(
                anchor=anchor,
                level=int(level) if level is not None else 2,
                position=int(position) if position is not None else 0,
            )
        return out

    def _current_tile_body(self, doc_id: str, tile_anchor: str) -> str:
        planned = self._planned.get((doc_id, tile_anchor))
        if planned is not None:
            return planned.body
        safe_doc = escape_sparql_literal(doc_id)
        safe_anchor = escape_sparql_literal(tile_anchor)
        sparql = (
            f"PREFIX cf: <{self._ns}> "
            "SELECT ?body WHERE { "
            f'?s a cf:Section ; cf:source_doc "{safe_doc}" ; '
            f'cf:section_anchor "{safe_anchor}" ; cf:narrative_body ?body }}'
        )
        for row in select_rows(self._txn.store, sparql):
            body = _strv(_row_lookup(row, "body"))
            if body is not None:
                return body
        raise KGValidationError(
            f"level-2 tile {tile_anchor!r} of document {doc_id!r} carries no "
            "narrative_body; re-ingest the document to restore it."
        )

    def _stored_contains(self, doc_id: str, anchor: str) -> list[str]:
        safe_doc = escape_sparql_literal(doc_id)
        safe_anchor = escape_sparql_literal(anchor)
        sparql = (
            f"PREFIX cf: <{self._ns}> "
            "SELECT ?eid WHERE { "
            f'?s a cf:Section ; cf:source_doc "{safe_doc}" ; '
            f'cf:section_anchor "{safe_anchor}" ; cf:contains_entity ?e . '
            "?e cf:entity_id ?eid }"
        )
        out: list[str] = []
        for row in select_rows(self._txn.store, sparql):
            eid = _strv(_row_lookup(row, "eid"))
            if eid is not None:
                out.append(eid)
        return sorted(out)
