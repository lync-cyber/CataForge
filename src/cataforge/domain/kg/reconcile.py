"""Per-doc_type drift detector between Markdown sources and the KG store.

Implements `cataforge kg reconcile`. For every doc_type in
`KGConfig.kg_active_doc_types`, the reconciler:

1. Scans `docs/{subdir}/*.md` using the same ingest pipeline as
   `cataforge kg import` (`scan_business_docs` → `extract_entities`
   → `extract_relations`).
2. Pulls the corresponding entities and traceability triples from the
   KG, attributed to a doc_type by the `cf:source_doc` literal of each
   entity (relations inherit their subject's source_doc).
3. Computes symmetric difference on entity_ids and on
   `(subject, predicate_curie, object)` triples.
4. Returns a structured report; non-empty divergence sets are surfaced
   as `missing_*` (FS-only) and `ghost_*` (KG-only) lists.

The doctor `kg_ingestion_completeness` gate runs an entity-only variant
of this check at deploy time; `reconcile` is the periodic operational
sweep that additionally covers relations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cataforge.domain.docs.index_ops import _load_doc_type_map
from cataforge.domain.kg._config import KGConfig
from cataforge.domain.kg._sparql_utils import (
    _row_lookup,
    _strv,
    cf_namespace,
    curie_for_iri,
    escape_sparql_literal,
)
from cataforge.domain.kg.ingest.entity_extract import extract_entities
from cataforge.domain.kg.ingest.relation_extract import extract_relations
from cataforge.domain.kg.ingest.scan import scan_business_docs
from cataforge.domain.kg.ingest.structure_extract import extract_structure

if TYPE_CHECKING:
    import pyoxigraph as ox


# Triple-key form used for set diffing. CURIE-normalized predicate so
# the FS-side `cf:implements` and the KG-side full IRI compare equal.
RelKey = tuple[str, str, str]  # (subject_entity_id, predicate_curie, object_entity_id)


@dataclass
class PerDocTypeReport:
    """Reconciliation outcome for a single doc_type."""

    doc_type: str
    missing_entities: list[str] = field(default_factory=list)
    ghost_entities: list[str] = field(default_factory=list)
    missing_relations: list[RelKey] = field(default_factory=list)
    ghost_relations: list[RelKey] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)
    ghost_sections: list[str] = field(default_factory=list)

    @property
    def divergence_count(self) -> int:
        return (
            len(self.missing_entities)
            + len(self.ghost_entities)
            + len(self.missing_relations)
            + len(self.ghost_relations)
            + len(self.missing_sections)
            + len(self.ghost_sections)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_type": self.doc_type,
            "missing_entities": sorted(self.missing_entities),
            "ghost_entities": sorted(self.ghost_entities),
            "missing_relations": [list(t) for t in sorted(self.missing_relations)],
            "ghost_relations": [list(t) for t in sorted(self.ghost_relations)],
            "missing_sections": sorted(self.missing_sections),
            "ghost_sections": sorted(self.ghost_sections),
            "divergence_count": self.divergence_count,
        }


@dataclass
class ReconcileReport:
    """Aggregate reconciliation outcome across every active doc_type."""

    timestamp: str
    active_doc_types: list[str]
    per_doc_type: dict[str, PerDocTypeReport] = field(default_factory=dict)

    @property
    def overall_divergence_count(self) -> int:
        return sum(r.divergence_count for r in self.per_doc_type.values())

    @property
    def ok(self) -> bool:
        return self.overall_divergence_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "active_doc_types": self.active_doc_types,
            "per_doc_type": {k: v.to_dict() for k, v in sorted(self.per_doc_type.items())},
            "overall_divergence_count": self.overall_divergence_count,
            "ok": self.ok,
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _kg_entities_for_doc_ids(store: ox.Store, config: KGConfig, doc_ids: set[str]) -> set[str]:
    """Return entity_ids in KG whose `cf:source_doc` is one of `doc_ids`."""
    if not doc_ids:
        return set()
    ns = cf_namespace(config)
    values_clause = " ".join(f'"{escape_sparql_literal(d)}"' for d in sorted(doc_ids))
    sparql = (
        f"PREFIX cf: <{ns}> "
        "SELECT DISTINCT ?entity_id WHERE { "
        f"  VALUES ?src {{ {values_clause} }} "
        "  ?s cf:entity_id ?entity_id ; "
        "     cf:source_doc ?src . "
        "}"
    )
    out: set[str] = set()
    for row in store.query(sparql):
        eid = _strv(_row_lookup(row, "entity_id"))
        if eid is not None:
            out.add(eid)
    return out


def _kg_relations_for_doc_ids(store: ox.Store, config: KGConfig, doc_ids: set[str]) -> set[RelKey]:
    """Return `(s_id, predicate_curie, o_id)` triples where the subject's
    `cf:source_doc` is one of `doc_ids`.

    Both subject and object are returned as entity_id strings so the
    diff against FS-extracted relations is direct. Edges to objects
    that lack a `cf:entity_id` literal are skipped (they should be
    caught by `kg validate` xref-target shape).
    """
    if not doc_ids:
        return set()
    ns = cf_namespace(config)
    values_clause = " ".join(f'"{escape_sparql_literal(d)}"' for d in sorted(doc_ids))
    sparql = (
        f"PREFIX cf: <{ns}> "
        "SELECT ?s_id ?p ?o_id WHERE { "
        f"  VALUES ?src {{ {values_clause} }} "
        "  ?s cf:entity_id ?s_id ; "
        "     cf:source_doc ?src ; "
        "     ?p ?o . "
        "  ?o cf:entity_id ?o_id . "
        f'  FILTER(STRSTARTS(STR(?p), "{ns}")) '
        # ?o cf:entity_id ?o_id above already filters to object-property
        # edges, so this branch only sees traceability predicates.
        "}"
    )
    out: set[RelKey] = set()
    for row in store.query(sparql):
        s_id = _strv(_row_lookup(row, "s_id"))
        p_iri = _strv(_row_lookup(row, "p"))
        o_id = _strv(_row_lookup(row, "o_id"))
        if s_id is None or p_iri is None or o_id is None:
            continue
        curie = curie_for_iri(p_iri, ns)
        if curie == "cf:belongs_to_project":
            continue
        out.add((s_id, curie, o_id))
    return out


def _kg_sections_for_doc_ids(store: ox.Store, config: KGConfig, doc_ids: set[str]) -> set[str]:
    """Return `cf:section_anchor` values of Section nodes whose
    `cf:source_doc` is one of `doc_ids`."""
    if not doc_ids:
        return set()
    ns = cf_namespace(config)
    values_clause = " ".join(f'"{escape_sparql_literal(d)}"' for d in sorted(doc_ids))
    sparql = (
        f"PREFIX cf: <{ns}> "
        "SELECT DISTINCT ?anchor WHERE { "
        f"  VALUES ?src {{ {values_clause} }} "
        "  ?s a cf:Section ; "
        "     cf:section_anchor ?anchor ; "
        "     cf:source_doc ?src . "
        "}"
    )
    out: set[str] = set()
    for row in store.query(sparql):
        anchor = _strv(_row_lookup(row, "anchor"))
        if anchor is not None:
            out.add(anchor)
    return out


def reconcile(
    store: ox.Store,
    project_root: Path,
    config: KGConfig,
) -> ReconcileReport:
    """Run per-doc_type drift detection.

    Active doc_types come from `config.kg_active_doc_types`. The legacy
    `_load_doc_type_map` resolves each doc_type to a `docs/<subdir>`
    path; `scan_business_docs` enforces the same parser as the import
    codemod, so the comparison is apples-to-apples.
    """
    project_root = Path(project_root)
    type_map = _load_doc_type_map(str(project_root))
    active = sorted(config.kg_active_doc_types)

    report = ReconcileReport(timestamp=_utc_now_iso(), active_doc_types=active)

    for doc_type in active:
        per = PerDocTypeReport(doc_type=doc_type)
        report.per_doc_type[doc_type] = per

        # Resolve the on-disk subdir; honour the framework.json override
        # the same way the legacy loader does.
        subdir = type_map.get(doc_type, doc_type)
        directory = project_root / "docs" / subdir
        if not directory.is_dir():
            # FS has nothing for this doc_type. Anything in KG attributed
            # to a doc_id under this doc_type would surface as ghost — but
            # we can't compute that without scanning, so we attribute
            # ghost entities at the per-doc_id level below.
            parsed: list = []
        else:
            parsed = scan_business_docs(project_root, [doc_type])

        # FS-side extraction
        fs_entities: set[str] = set()
        fs_relations: set[RelKey] = set()
        fs_sections: set[str] = set()
        doc_ids: set[str] = set()
        for doc in parsed:
            doc_ids.add(doc.doc_id)
            doc_entities = extract_entities(doc)
            for entity in doc_entities:
                fs_entities.add(entity.entity_id)
            for relation in extract_relations(doc):
                fs_relations.add(
                    (
                        relation.subject_entity_id,
                        relation.predicate_curie,
                        relation.object_entity_id,
                    )
                )
            _document, doc_sections = extract_structure(doc, doc_entities)
            for section in doc_sections:
                fs_sections.add(section.anchor)

        # If no parsed docs but the doc_type has a built-in subdir name,
        # still consult KG by the subdir-as-doc_id (cheap; usually empty).
        if not doc_ids:
            doc_ids = {subdir, doc_type}

        kg_entities = _kg_entities_for_doc_ids(store, config, doc_ids)
        kg_relations = _kg_relations_for_doc_ids(store, config, doc_ids)
        kg_sections = _kg_sections_for_doc_ids(store, config, doc_ids)

        per.missing_entities = sorted(fs_entities - kg_entities)
        per.ghost_entities = sorted(kg_entities - fs_entities)
        per.missing_relations = sorted(fs_relations - kg_relations)
        per.ghost_relations = sorted(kg_relations - fs_relations)
        per.missing_sections = sorted(fs_sections - kg_sections)
        per.ghost_sections = sorted(kg_sections - fs_sections)

    return report


def write_report(report: ReconcileReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


__all__ = [
    "PerDocTypeReport",
    "ReconcileReport",
    "RelKey",
    "reconcile",
    "write_report",
]
