"""Post-cutover audit: KG content hash vs current Markdown source.

A diagnostic check, not a gating mechanism. For each active doc_type,
sample N entities; for each sampled entity:

* recompute the section content hash from the current on-disk Markdown
  using the same `extract_entities` pipeline that ran at ingest time;
* fetch the `cf:content_hash` literal stored in KG for the same entity;
* if they differ → emit an alarm with both digests.

Alarms surface but never affect the exit code. The recommended response
to a persistent alarm on a doc_type is to remove that doc_type from
`kg_active_doc_types` and re-ingest.

Content-hash diffing detects material content drift and reuses the
canonical hash the ingest pipeline already records.

Sampling uses Python stdlib `random.Random` so `--seed` yields
reproducible audits.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cataforge.kg._ask import ask
from cataforge.kg._sparql_utils import _row_lookup, _strv, cf_namespace
from cataforge.kg.ingest.entity_extract import extract_entities
from cataforge.kg.ingest.iri import entity_iri
from cataforge.kg.ingest.scan import scan_business_docs

if TYPE_CHECKING:
    from cataforge.kg.facade import KnowledgeGraph


@dataclass
class CompareReadAlarm:
    """A single entity whose stored hash diverged from the live source."""

    entity_id: str
    doc_type: str
    source_doc: str
    kg_content_hash: str | None
    fs_content_hash: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "doc_type": self.doc_type,
            "source_doc": self.source_doc,
            "kg_content_hash": self.kg_content_hash,
            "fs_content_hash": self.fs_content_hash,
            "reason": self.reason,
        }


@dataclass
class CompareReadReport:
    """Outcome of one `compare-read` run across one or more doc_types."""

    sampled_count: int
    alarms: list[CompareReadAlarm] = field(default_factory=list)
    per_doc_type_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sampled_count": self.sampled_count,
            "alarms": [a.to_dict() for a in self.alarms],
            "per_doc_type_counts": dict(sorted(self.per_doc_type_counts.items())),
        }


def _kg_content_hash(kg: KnowledgeGraph, entity_id: str) -> str | None:
    """Read the `cf:content_hash` literal stored in KG for `entity_id`."""
    ns = cf_namespace(kg.config)
    iri = entity_iri(entity_id, kg.config.base_namespace)
    sparql = f"PREFIX cf: <{ns}> SELECT ?h WHERE {{ <{iri}> cf:content_hash ?h }} LIMIT 1"
    for row in kg.store.query(sparql):
        return _strv(_row_lookup(row, "h"))
    return None


def _kg_entity_exists(kg: KnowledgeGraph, entity_id: str) -> bool:
    ns = cf_namespace(kg.config)
    iri = entity_iri(entity_id, kg.config.base_namespace)
    return ask(
        kg.store,
        f"PREFIX cf: <{ns}> ASK {{ <{iri}> cf:entity_id ?e }}",
    )


def compare_read(
    kg: KnowledgeGraph,
    project_root: Path,
    *,
    doc_types: set[str],
    sample_size: int = 20,
    seed: int | None = None,
) -> CompareReadReport:
    """Sample-audit KG content hashes against the live filesystem.

    Content-hash equality is binary: any digest mismatch is an alarm;
    any FS-extracted entity missing from KG is an alarm (reason
    ``kg-missing-entity``).

    The sample pool is the union of every entity the FS scan finds
    under each active doc_type, ordered deterministically by entity_id
    for reproducibility with ``seed``.
    """
    project_root = Path(project_root)

    # FS-side pool: rerun the ingest extraction phase to get authoritative
    # current-content hashes.
    fs_entities: list[tuple[str, str, str, str]] = []
    # (entity_id, doc_type, source_doc, fs_content_hash)
    for doc_type in sorted(doc_types):
        parsed = scan_business_docs(project_root, [doc_type])
        seen: set[str] = set()
        for doc in parsed:
            for entity in extract_entities(doc):
                if entity.entity_id in seen:
                    continue
                seen.add(entity.entity_id)
                fs_entities.append(
                    (
                        entity.entity_id,
                        doc_type,
                        doc.doc_id,
                        entity.content_hash,
                    )
                )

    # Deterministic ordering so RNG seeding is meaningful.
    fs_entities.sort(key=lambda t: (t[1], t[0]))

    rng = random.Random(seed)
    if sample_size <= 0 or sample_size >= len(fs_entities):
        sample = list(fs_entities)
    else:
        sample = rng.sample(fs_entities, k=sample_size)

    report = CompareReadReport(sampled_count=len(sample))

    for entity_id, doc_type, source_doc, fs_hash in sample:
        report.per_doc_type_counts[doc_type] = report.per_doc_type_counts.get(doc_type, 0) + 1
        kg_hash = _kg_content_hash(kg, entity_id)
        if kg_hash is None:
            if _kg_entity_exists(kg, entity_id):
                # Entity exists but lacks cf:content_hash — schema requires
                # it (the writer always populates), so missing means
                # something corrupted the store.
                report.alarms.append(
                    CompareReadAlarm(
                        entity_id=entity_id,
                        doc_type=doc_type,
                        source_doc=source_doc,
                        kg_content_hash=None,
                        fs_content_hash=fs_hash,
                        reason="kg-content-hash-absent",
                    )
                )
            else:
                report.alarms.append(
                    CompareReadAlarm(
                        entity_id=entity_id,
                        doc_type=doc_type,
                        source_doc=source_doc,
                        kg_content_hash=None,
                        fs_content_hash=fs_hash,
                        reason="kg-missing-entity",
                    )
                )
            continue
        if kg_hash != fs_hash:
            report.alarms.append(
                CompareReadAlarm(
                    entity_id=entity_id,
                    doc_type=doc_type,
                    source_doc=source_doc,
                    kg_content_hash=kg_hash,
                    fs_content_hash=fs_hash,
                    reason="content-hash-mismatch",
                )
            )

    report.alarms.sort(key=lambda a: (a.doc_type, a.entity_id))
    return report


__all__ = [
    "CompareReadAlarm",
    "CompareReadReport",
    "compare_read",
]
