"""Phase 6 of task-7 §7.2: post-write integrity verification."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cataforge.kg._ask import ask
from cataforge.kg._config import KGConfig
from cataforge.kg.ingest.entity_extract import ExtractedEntity
from cataforge.kg.ingest.iri import entity_iri
from cataforge.kg.ingest.relation_extract import ExtractedRelation

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
    sparql = (
        f"PREFIX cf: <{namespace}> "
        "SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s a ?cls "
        "FILTER(STRSTARTS(STR(?cls), STR(cf:))) "
        "FILTER(?cls != cf:Project) }"
    )
    rows = list(store.query(sparql))
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
    namespace = config.ontology_namespace.rstrip("/") + "/"
    base_ns = config.base_namespace
    result = VerifyResult(
        entity_count_expected=len({e.entity_id for e in entities}),
        relation_count_expected=len(
            {
                (r.subject_entity_id, r.predicate_curie, r.object_entity_id)
                for r in relations
            }
        ),
    )

    result.entity_count_kg = _count_typed_subjects(store, namespace)

    # Relation count: count distinct (s, p, o) triples whose predicate is
    # a cf:* slot used for traceability. Filter out type / literal slots.
    traceability_predicates = sorted(
        {r.predicate_curie for r in relations}
    )
    if traceability_predicates:
        union = " UNION ".join(
            f"{{ ?s <{namespace}{c.split(':', 1)[1]}> ?o }}"
            for c in traceability_predicates
        )
        sparql = f"SELECT (COUNT(*) AS ?n) WHERE {{ {union} }}"
        rows = list(store.query(sparql))
        result.relation_count_kg = (
            int(rows[0]["n"].value) if rows and rows[0]["n"] is not None else 0
        )

    # Content-hash mismatches per extracted entity.
    for entity in entities:
        iri = entity_iri(entity.entity_id, base_ns)
        sparql = (
            f"PREFIX cf: <{namespace}> "
            f'ASK {{ <{iri}> cf:content_hash "{entity.content_hash}" }}'
        )
        if not ask(store, sparql):
            result.content_hash_mismatches.append(entity.entity_id)

        # Missing-entity check.
        sparql = f"ASK {{ <{iri}> ?p ?o }}"
        if not ask(store, sparql):
            result.missing_entities.append(entity.entity_id)

    return result
