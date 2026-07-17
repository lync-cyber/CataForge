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
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from cataforge.domain.kg._errors import KGEntityNotFoundError, KGValidationError
from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _strv,
    assert_safe_iri,
    cf_namespace,
    escape_sparql_literal,
    select_rows,
)
from cataforge.domain.kg.ingest.scan import heading_spans

if TYPE_CHECKING:
    from cataforge.domain.kg.ingest.entity_extract import ExtractedEntity, PrefixRegistry
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


@dataclass(frozen=True)
class SectionEntitySync:
    """Extraction context for syncing sub-entities during a narrative flush."""

    project_iri: str
    authority: Mapping[str, frozenset[str]]
    registry: PrefixRegistry
    mtime: float


@dataclass
class FlushOutcome:
    """One flush's write set plus the bookkeeping a caller needs to undo it.

    ``written_ids`` carries the synced entity ids/IRIs for post-commit
    validation scoping; ``delete_ids`` + ``prior_quads`` compensate the whole
    write (sections and entities) back to the pre-transaction state.
    """

    written_ids: set[str] = field(default_factory=set)
    delete_ids: list[str] = field(default_factory=list)
    prior_quads: list[Any] = field(default_factory=list)


def parse_tile_docs(
    doc_id: str,
    doc_type: str,
    tile_bodies: Iterable[str],
    *,
    mtime: float = 0.0,
) -> list[Any]:
    """Parse level-2 tile bodies as standalone mini ``ParsedDoc``s.

    Every level-2 tile embeds its subsections verbatim, so parsing tiles in
    isolation yields the same per-section ownership as a whole-document
    parse — one extraction semantics for ingest, write-doc, and narrative
    writes.
    """
    from cataforge.domain.kg.ingest.scan import parse_doc_text

    docs = []
    for body in tile_bodies:
        doc = parse_doc_text(
            body,
            doc_type=doc_type,
            file_name=f"{doc_id}.md",
            source_path=f"{doc_id}.md",
            mtime=mtime,
        )
        doc.doc_id = doc_id
        doc.doc_type = doc_type
        docs.append(doc)
    return docs


def extract_tile_entities(
    doc_id: str,
    doc_type: str,
    tile_bodies: Iterable[str],
    *,
    authority: Mapping[str, frozenset[str]],
    registry: PrefixRegistry,
    mtime: float = 0.0,
) -> list[ExtractedEntity]:
    """Run the ingest entity extractor over level-2 tile bodies.

    Duplicate (parent, entity_id) definitions keep the first occurrence,
    matching :func:`extract_entities` within one document.
    """
    from cataforge.domain.kg.ingest.entity_extract import extract_entities

    seen: dict[tuple[str | None, str], ExtractedEntity] = {}
    for doc in parse_tile_docs(doc_id, doc_type, tile_bodies, mtime=mtime):
        for entity in extract_entities(doc, authority=authority, registry=registry):
            seen.setdefault((entity.parent_id, entity.entity_id), entity)
    return list(seen.values())


def clear_stale_authored_relations(
    txn: TransactionContext,
    store: Any,
    cfg: Any,
    relations: list[Any],
    staged_iris: dict[str, str],
) -> None:
    """Stage removal of traceability edges the source no longer declares.

    Relation edges carry no source-doc provenance and are written add-if-absent,
    so an edge whose subject entity is unchanged across a re-author survives even
    after the source drops it. Every traceability edge's subject is an entity
    the authored scope defines, so clearing each authored subject's edges that
    are not in the freshly extracted set replaces the scope's edges atomically
    without touching structural predicates (``cf:part_of``) or other subjects'
    edges.
    """
    import pyoxigraph as ox  # noqa: PLC0415

    from cataforge.domain.kg._quads import _slot_iri, quads_for_subject
    from cataforge.domain.kg.ingest.iri import entity_iri
    from cataforge.domain.kg.ingest.relation_extract import TRACEABILITY_PREDICATE_CURIES

    ns = cf_namespace(cfg)
    predicate_iris = {_slot_iri(curie, ns) for curie in TRACEABILITY_PREDICATE_CURIES}
    fresh: set[tuple[str, str, str]] = set()
    for relation in relations:
        subject_iri = staged_iris.get(relation.subject_entity_id) or entity_iri(
            relation.subject_entity_id, cfg.base_namespace
        )
        object_iri = staged_iris.get(relation.object_entity_id) or entity_iri(
            relation.object_entity_id, cfg.base_namespace
        )
        fresh.add((subject_iri, _slot_iri(relation.predicate_curie, ns), object_iri))

    for subject_iri in set(staged_iris.values()):
        for quad in quads_for_subject(store, subject_iri):
            predicate = quad.predicate.value
            obj = quad.object
            if predicate not in predicate_iris or not isinstance(obj, ox.NamedNode):
                continue
            if (subject_iri, predicate, obj.value) in fresh:
                continue
            txn.remove(quad)


def stage_authored_relations(
    txn: TransactionContext,
    relations: list[Any],
    cfg: Any,
    staged_iris: dict[str, str],
) -> None:
    """Stage each relation, resolving endpoints against the in-flight IRI map.

    Subordinate endpoints are not yet committed, so a store-querying resolution
    would miss them; the staged-IRI map is consulted first and the flat entity
    IRI is the fallback.
    """
    from cataforge.domain.kg.ingest.iri import entity_iri

    for relation in relations:
        subject_iri = staged_iris.get(relation.subject_entity_id) or entity_iri(
            relation.subject_entity_id, cfg.base_namespace
        )
        object_iri = staged_iris.get(relation.object_entity_id) or entity_iri(
            relation.object_entity_id, cfg.base_namespace
        )
        txn.add_relation(
            relation.subject_entity_id,
            relation.predicate_curie,
            relation.object_entity_id,
            subject_iri=subject_iri,
            object_iri=object_iri,
        )


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

    def __init__(
        self, txn: TransactionContext, *, entity_sync: SectionEntitySync | None = None
    ) -> None:
        self._txn = txn
        self._ns = cf_namespace(txn.config)
        self._entity_sync = entity_sync
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

    def flush(self) -> FlushOutcome:
        """Stage the planned deletes/upserts plus the sub-entity sync.

        The rewritten sections' business entities are re-extracted with the
        same semantics ingest and write-doc use, then diff-merged: new
        definitions are staged, changed ones replaced (their pre-existing
        outgoing traceability edges re-staged across the replace), and
        entities the rewritten text no longer defines are deleted. The
        returned :class:`FlushOutcome` lets the caller validate and, on
        violation, compensate the entire write.
        """
        from cataforge.domain.kg.ingest.iri import section_iri

        base_ns = self._txn.config.base_namespace
        outcome = FlushOutcome()
        fresh_by_doc, contains_map = self._plan_entity_sync()

        for doc_id, anchor in sorted(self._deletes - set(self._planned)):
            outcome.prior_quads.extend(self._node_prior_quads(section_iri(doc_id, anchor, base_ns)))
            try:
                self._txn.delete_entity(f"doc/{doc_id}/sec/{anchor}", cascade=True)
            except KGEntityNotFoundError:
                continue
        for (doc_id, anchor), plan in self._planned.items():
            outcome.prior_quads.extend(self._node_prior_quads(section_iri(doc_id, anchor, base_ns)))
            outcome.delete_ids.append(f"doc/{doc_id}/sec/{anchor}")
            if plan.explicit_contains is not None:
                contains = plan.explicit_contains
            elif (doc_id, anchor) in contains_map:
                contains = contains_map[(doc_id, anchor)]
            else:
                contains = self._stored_contains(doc_id, anchor)
            self._txn.add_section(
                doc_id,
                anchor,
                plan.body,
                _sha256(plan.body),
                level=plan.level,
                title=anchor,
                contained_entity_ids=contains,
            )
        self._sync_entities(fresh_by_doc, outcome)
        return outcome

    # -- sub-entity sync -------------------------------------------------------

    def _plan_entity_sync(
        self,
    ) -> tuple[
        dict[str, tuple[list[ExtractedEntity], list[Any]] | None],
        dict[tuple[str, str], list[str]],
    ]:
        """Extract each planned doc's fresh entities/relations and contains.

        A doc whose Document node (and thus doc_type) is absent maps to
        ``None`` — the sync is skipped for it and the stored contains edges
        are carried over unchanged.
        """
        from cataforge.domain.kg.ingest.entity_extract import extract_entities
        from cataforge.domain.kg.ingest.relation_extract import extract_relations

        fresh_by_doc: dict[str, tuple[list[ExtractedEntity], list[Any]] | None] = {}
        contains_map: dict[tuple[str, str], list[str]] = {}
        if self._entity_sync is None:
            return fresh_by_doc, contains_map
        for doc_id in sorted({d for (d, _a) in self._planned}):
            doc_type = self._document_doc_type(doc_id)
            if doc_type is None:
                fresh_by_doc[doc_id] = None
                continue
            tiles = [p.body for (d, _a), p in self._planned.items() if d == doc_id and p.level == 2]
            entity_seen: dict[tuple[str | None, str], ExtractedEntity] = {}
            relation_seen: dict[tuple[str, str, str], Any] = {}
            for doc in parse_tile_docs(doc_id, doc_type, tiles, mtime=self._entity_sync.mtime):
                for entity in extract_entities(
                    doc,
                    authority=self._entity_sync.authority,
                    registry=self._entity_sync.registry,
                ):
                    entity_seen.setdefault((entity.parent_id, entity.entity_id), entity)
                for relation in extract_relations(doc, self._entity_sync.registry):
                    key = (
                        relation.subject_entity_id,
                        relation.predicate_curie,
                        relation.object_entity_id,
                    )
                    relation_seen.setdefault(key, relation)
            fresh = list(entity_seen.values())
            fresh_by_doc[doc_id] = (fresh, list(relation_seen.values()))
            owned: dict[str, list[str]] = {}
            for entity in fresh:
                owned.setdefault(entity.source_section, []).append(entity.entity_id)
            for d, anchor in self._planned:
                if d == doc_id:
                    contains_map[(d, anchor)] = sorted(owned.get(anchor, []))
        return fresh_by_doc, contains_map

    def _sync_entities(
        self,
        fresh_by_doc: dict[str, tuple[list[ExtractedEntity], list[Any]] | None],
        outcome: FlushOutcome,
    ) -> None:
        """Diff-merge each doc's fresh entity and relation sets against the store.

        Relations follow the write-doc contract: each fresh subject's
        traceability edges are re-derived from the rewritten text (declared
        edges staged, undeclared ones cleared) — the one extraction semantics
        both authoring doors share.
        """
        from cataforge.domain.kg.ingest.iri import resolve_entity_iri
        from cataforge.domain.kg.ingest.writer import _entity_title

        sync = self._entity_sync
        if sync is None:
            return

        base_ns = self._txn.config.base_namespace
        for doc_id, fresh_pair in fresh_by_doc.items():
            if fresh_pair is None:
                continue
            fresh, fresh_relations = fresh_pair
            fresh_keys = {e.scope_key for e in fresh}
            # The stale set is fixed before staging: entities homed in the
            # rewritten/deleted sections whose definitions the new text no
            # longer carries. Anchors duplicated across tiles are excluded —
            # `cf:source_section` is a heading literal, so their homes are
            # ambiguous and deletion could hit another tile's entities.
            affected = {a for (d, a) in set(self._planned) | self._deletes if d == doc_id}
            cleanup_anchors = affected - self._ambiguous_child_anchors(doc_id)
            stale = [
                (scoped_id, iri)
                for scoped_id, iri in self._entities_homed_at(doc_id, cleanup_anchors)
                if scoped_id not in fresh_keys and iri not in self._txn.staged_entity_iris
            ]
            staged_iris_map: dict[str, str] = {}
            for entity in fresh:
                iri = resolve_entity_iri(
                    entity.entity_id, entity.class_name, entity.parent_id, base_ns
                )
                if iri in self._txn.staged_entity_iris:
                    continue  # an explicit add_entity op in this txn wins
                prior = self._node_prior_quads(iri)
                self._txn.add_entity(
                    entity.entity_id,
                    entity.class_name,
                    _entity_title(entity),
                    entity.source_doc,
                    entity.source_section,
                    entity.content_hash,
                    sync.project_iri,
                    parent_id=entity.parent_id,
                    extra_slots=entity.extra_slots or None,
                    mtime=entity.mtime,
                    attributes=entity.attributes or None,
                )
                staged_iris_map[entity.entity_id] = iri
                outcome.prior_quads.extend(prior)
                outcome.delete_ids.append(
                    f"{entity.parent_id}/{entity.entity_id}"
                    if entity.parent_id
                    else entity.entity_id
                )
                outcome.written_ids.update({entity.entity_id, iri})
            clear_stale_authored_relations(
                self._txn, self._txn.store, self._txn.config, fresh_relations, staged_iris_map
            )
            stage_authored_relations(self._txn, fresh_relations, self._txn.config, staged_iris_map)
            for scoped_id, iri in stale:
                prior = self._node_prior_quads(iri)
                try:
                    self._txn.delete_entity(scoped_id, cascade=True)
                except KGEntityNotFoundError:
                    continue
                outcome.prior_quads.extend(prior)

    def _ambiguous_child_anchors(self, doc_id: str) -> set[str]:
        """Anchors appearing in more than one of the document's level-2 tiles.

        Planned bodies override the stored ones for their tile anchor; the
        remaining tiles come from the store. An anchor owned by two tiles has
        no unambiguous entity home, so callers must not treat it as a cleanup
        scope.
        """
        bodies: dict[str, str] = dict(self._stored_tile_bodies(doc_id))
        for (d, anchor), plan in self._planned.items():
            if d == doc_id and plan.level == 2:
                bodies[anchor] = plan.body
        counts: dict[str, int] = {}
        for tile_anchor, body in bodies.items():
            titles = {span.title.strip() for span in heading_spans(body, 0)}
            titles.discard(tile_anchor)
            for title in titles:
                if title:
                    counts[title] = counts.get(title, 0) + 1
        return {anchor for anchor, n in counts.items() if n > 1}

    def _stored_tile_bodies(self, doc_id: str) -> list[tuple[str, str]]:
        """``(anchor, narrative_body)`` of the document's stored level-2 tiles."""
        safe = escape_sparql_literal(doc_id)
        sparql = (
            f"PREFIX cf: <{self._ns}> "
            "SELECT ?anchor ?level ?body WHERE { "
            f'?s a cf:Section ; cf:source_doc "{safe}" ; '
            "cf:section_anchor ?anchor ; cf:narrative_body ?body . "
            "OPTIONAL { ?s cf:section_level ?level } }"
        )
        out: list[tuple[str, str]] = []
        for row in select_rows(self._txn.store, sparql):
            anchor = _strv(_row_lookup(row, "anchor"))
            body = _strv(_row_lookup(row, "body"))
            if anchor is None or body is None:
                continue
            level = _strv(_row_lookup(row, "level"))
            if (int(level) if level is not None else 2) == 2:
                out.append((anchor, body))
        return out

    def _document_doc_type(self, doc_id: str) -> str | None:
        from cataforge.domain.kg.ingest.iri import document_iri

        doc_iri = document_iri(doc_id, self._txn.config.base_namespace)
        sparql = (
            f"PREFIX cf: <{self._ns}> "
            f"SELECT ?t WHERE {{ <{assert_safe_iri(doc_iri)}> cf:doc_type ?t }} LIMIT 1"
        )
        for row in select_rows(self._txn.store, sparql):
            return _strv(_row_lookup(row, "t"))
        return None

    def _entities_homed_at(self, doc_id: str, anchors: set[str]) -> list[tuple[str, str]]:
        """``(scope_key, iri)`` of stored entities homed in the given sections.

        Scope keys are built from ``cf:entity_id`` + the ``cf:part_of`` parent
        (subordinates only carry that edge), not by slicing the IRI — the
        instance namespace is project-configurable, so IRI surgery is not a
        stable identity source.
        """
        if not anchors:
            return []
        safe_doc = escape_sparql_literal(doc_id)
        values = " ".join(f'"{escape_sparql_literal(a)}"' for a in sorted(anchors))
        sparql = (
            f"PREFIX cf: <{self._ns}> "
            "SELECT DISTINCT ?s ?eid ?parent_id WHERE { "
            f"  VALUES ?sec {{ {values} }} "
            f'  ?s a ?cls ; cf:entity_id ?eid ; cf:source_doc "{safe_doc}" ; '
            "     cf:source_section ?sec . "
            "  OPTIONAL { ?s cf:part_of ?p . ?p cf:entity_id ?parent_id . } "
            f"  FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
            "}"
        )
        out: list[tuple[str, str]] = []
        for row in select_rows(self._txn.store, sparql):
            iri = _strv(_row_lookup(row, "s"))
            eid = _strv(_row_lookup(row, "eid"))
            if iri is None or eid is None:
                continue
            parent_id = _strv(_row_lookup(row, "parent_id"))
            out.append((f"{parent_id}/{eid}" if parent_id else eid, iri))
        return out

    def _node_prior_quads(self, iri: str) -> list[Any]:
        """Pre-transaction snapshot of every quad touching ``iri``."""
        from cataforge.domain.kg._quads import (
            attribute_subject_quads,
            quads_for_subject,
            quads_targeting,
        )

        quads = list(quads_for_subject(self._txn.store, iri))
        quads.extend(attribute_subject_quads(self._txn.store, iri, self._ns))
        quads.extend(quads_targeting(self._txn.store, iri))
        return quads

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
