"""Phase 6: post-write integrity verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cataforge.domain.kg._ask import ask
from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._sparql_utils import (
    assert_safe_iri,
    cf_namespace,
    escape_sparql_literal,
    select_rows,
)
from cataforge.domain.kg.ingest.entity_extract import ExtractedEntity
from cataforge.domain.kg.ingest.iri import resolve_entity_iri
from cataforge.domain.kg.ingest.relation_extract import ExtractedRelation

if TYPE_CHECKING:
    import pyoxigraph as ox


@dataclass
class VerifyResult:
    """Outcome of phase 6 — empty errors list means OK."""

    entity_count_kg: int = 0
    entity_count_expected: int = 0
    relation_count_kg: int = 0
    relation_count_expected: int = 0
    content_hash_mismatches: list[str] = field(default_factory=list)
    missing_entities: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            self.entity_count_kg == self.entity_count_expected
            and self.relation_count_kg == self.relation_count_expected
            and not self.content_hash_mismatches
            and not self.missing_entities
        )


def _count_typed_subjects(store: ox.Store, namespace: str) -> int:
    # Business entities only — they carry a `cf:entity_id`. Project and the
    # structural container nodes (Document / Volume / Section) are identified
    # by their `id` IRI and are excluded by requiring the entity_id literal.
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a ?cls ; cf:entity_id ?eid "
        "FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
        "FILTER(?cls != cf:Project) }"
    )
    rows = list(select_rows(store, sparql))
    if not rows:
        return 0
    n_value = rows[0]["n"]
    return int(n_value.value) if n_value is not None else 0


def verify_after_write(
    store: ox.Store,
    entities: list[ExtractedEntity],
    relations: list[ExtractedRelation],
    config: KGConfig,
) -> VerifyResult:
    namespace = cf_namespace(config)
    base_ns = config.base_namespace
    result = VerifyResult(
        entity_count_expected=len({(e.parent_id, e.entity_id) for e in entities}),
        relation_count_expected=len(
            {(r.subject_entity_id, r.predicate_curie, r.object_entity_id) for r in relations}
        ),
    )

    result.entity_count_kg = _count_typed_subjects(store, namespace)

    # Relation count: count distinct (s, p, o) triples whose predicate is
    # a cf:* slot used for traceability. Filter out type / literal slots.
    traceability_predicates = sorted({r.predicate_curie for r in relations})
    if traceability_predicates:
        union = " UNION ".join(
            f"{{ ?s <{namespace}{c.split(':', 1)[1]}> ?o }}" for c in traceability_predicates
        )
        sparql = f"SELECT (COUNT(*) AS ?n) WHERE {{ {union} }}"
        rows = list(select_rows(store, sparql))
        result.relation_count_kg = (
            int(rows[0]["n"].value) if rows and rows[0]["n"] is not None else 0
        )

    for entity in entities:
        iri = resolve_entity_iri(entity.entity_id, entity.class_name, entity.parent_id, base_ns)
        safe_iri = assert_safe_iri(iri)

        presence_sparql = f"ASK {{ <{safe_iri}> ?p ?o }}"
        if not ask(store, presence_sparql):
            result.missing_entities.append(entity.entity_id)
            continue

        safe_hash = escape_sparql_literal(entity.content_hash)
        hash_sparql = (
            f'PREFIX cf: <{namespace}> ASK {{ <{safe_iri}> cf:content_hash "{safe_hash}" }}'
        )
        if not ask(store, hash_sparql):
            result.content_hash_mismatches.append(entity.entity_id)

    return result
