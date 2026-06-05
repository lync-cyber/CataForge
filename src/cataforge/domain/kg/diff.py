"""Semantic diff between two KG snapshots.

Implements `cataforge kg diff SNAPSHOT_A SNAPSHOT_B`. Each snapshot is an
NQuads file produced by `cataforge kg snapshot`. Both are parsed into
in-memory stores; the diff is computed at the **entity / relation** level,
not on raw triples, so the `rdfs:subClassOf` bootstrap axioms shared by
every store never surface as noise.

An entity is keyed by its `cf:entity_id`. `modified` means the entity is
present in both snapshots but its `cf:content_hash` changed — a content
edit, the operationally interesting signal. Relations are keyed
`(subject_entity_id, predicate_curie, object_entity_id)`, mirroring the
`reconcile` triple form so the two reports read alike.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _strv,
    cf_namespace,
    curie_for_iri,
    select_rows,
)

if TYPE_CHECKING:
    import pyoxigraph as ox

RelKey = tuple[str, str, str]  # (subject_entity_id, predicate_curie, object_entity_id)

# Project-membership edges are structural, not traceability; reconcile drops
# them from its relation diff and this diff matches that for parity.
_STRUCTURAL_PREDICATES = frozenset({"cf:belongs_to_project"})


@dataclass
class SnapshotDiff:
    """Entity- and relation-level delta from snapshot A to snapshot B."""

    added_entities: list[str] = field(default_factory=list)
    removed_entities: list[str] = field(default_factory=list)
    modified_entities: list[str] = field(default_factory=list)
    added_relations: list[RelKey] = field(default_factory=list)
    removed_relations: list[RelKey] = field(default_factory=list)

    @property
    def divergence_count(self) -> int:
        return (
            len(self.added_entities)
            + len(self.removed_entities)
            + len(self.modified_entities)
            + len(self.added_relations)
            + len(self.removed_relations)
        )

    @property
    def ok(self) -> bool:
        return self.divergence_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "added_entities": sorted(self.added_entities),
            "removed_entities": sorted(self.removed_entities),
            "modified_entities": sorted(self.modified_entities),
            "added_relations": [list(t) for t in sorted(self.added_relations)],
            "removed_relations": [list(t) for t in sorted(self.removed_relations)],
            "divergence_count": self.divergence_count,
            "ok": self.ok,
        }


def _load_snapshot_store(path: Path) -> ox.Store:
    """Parse an NQuads snapshot file into a fresh in-memory store."""
    import pyoxigraph as ox  # noqa: PLC0415

    store = ox.Store()
    for quad in ox.parse(Path(path).read_bytes(), ox.RdfFormat.N_QUADS):
        store.add(quad)
    return store


def _entities_with_hash(store: ox.Store, namespace: str) -> dict[str, str]:
    """Return `{entity_id: content_hash}` for every entity in the store.

    Entities without a `cf:content_hash` map to the empty string, so two
    such entities compare equal (unmodified) rather than spuriously modified.
    """
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT ?id ?hash WHERE { "
        "  ?s cf:entity_id ?id . "
        "  OPTIONAL { ?s cf:content_hash ?hash } "
        "}"
    )
    out: dict[str, str] = {}
    for row in select_rows(store, sparql):
        eid = _strv(_row_lookup(row, "id"))
        if eid is None:
            continue
        out[eid] = _strv(_row_lookup(row, "hash")) or ""
    return out


def _relations(store: ox.Store, namespace: str) -> set[RelKey]:
    """Return every `(s_id, predicate_curie, o_id)` traceability edge.

    Both endpoints carry a `cf:entity_id`; the object binding filters out
    literal-valued slots, leaving only object-property edges. Structural
    project-membership edges are excluded for reconcile parity.
    """
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT ?s_id ?p ?o_id WHERE { "
        "  ?s cf:entity_id ?s_id ; ?p ?o . "
        "  ?o cf:entity_id ?o_id . "
        f'  FILTER(STRSTARTS(STR(?p), "{namespace}")) '
        "}"
    )
    out: set[RelKey] = set()
    for row in select_rows(store, sparql):
        s_id = _strv(_row_lookup(row, "s_id"))
        p_iri = _strv(_row_lookup(row, "p"))
        o_id = _strv(_row_lookup(row, "o_id"))
        if s_id is None or p_iri is None or o_id is None:
            continue
        curie = curie_for_iri(p_iri, namespace)
        if curie in _STRUCTURAL_PREDICATES:
            continue
        out.add((s_id, curie, o_id))
    return out


def diff_snapshots(
    snapshot_a: Path,
    snapshot_b: Path,
    *,
    namespace: str | None = None,
) -> SnapshotDiff:
    """Compute the entity/relation delta from `snapshot_a` to `snapshot_b`.

    "added" / "removed" are relative to A: present in B but not A is added;
    present in A but not B is removed. `namespace` defaults to the canonical
    cf: ontology namespace.
    """
    ns = namespace or cf_namespace(KGConfig())
    store_a = _load_snapshot_store(Path(snapshot_a))
    store_b = _load_snapshot_store(Path(snapshot_b))

    ent_a = _entities_with_hash(store_a, ns)
    ent_b = _entities_with_hash(store_b, ns)
    ids_a, ids_b = set(ent_a), set(ent_b)

    rel_a = _relations(store_a, ns)
    rel_b = _relations(store_b, ns)

    return SnapshotDiff(
        added_entities=sorted(ids_b - ids_a),
        removed_entities=sorted(ids_a - ids_b),
        modified_entities=sorted(i for i in ids_a & ids_b if ent_a[i] != ent_b[i]),
        added_relations=sorted(rel_b - rel_a),
        removed_relations=sorted(rel_a - rel_b),
    )


def render_diff_text(diff: SnapshotDiff) -> str:
    """Human-readable summary grouped by `+ added`, `- removed`, `~ modified`."""
    lines: list[str] = []

    def _section(title: str, marker: str, items: list[Any]) -> None:
        if not items:
            return
        lines.append(f"{title} ({len(items)}):")
        for item in items:
            if isinstance(item, tuple):
                s_id, pred, o_id = item
                lines.append(f"  {marker} {s_id} {pred} {o_id}")
            else:
                lines.append(f"  {marker} {item}")

    _section("Added entities", "+", diff.added_entities)
    _section("Removed entities", "-", diff.removed_entities)
    _section("Modified entities", "~", diff.modified_entities)
    _section("Added relations", "+", diff.added_relations)
    _section("Removed relations", "-", diff.removed_relations)

    if not lines:
        return "No differences (snapshots are semantically identical)."
    return "\n".join(lines)


def render_diff_json(diff: SnapshotDiff) -> str:
    return json.dumps(diff.to_dict(), indent=2, ensure_ascii=False)


__all__ = [
    "RelKey",
    "SnapshotDiff",
    "diff_snapshots",
    "render_diff_json",
    "render_diff_text",
]
