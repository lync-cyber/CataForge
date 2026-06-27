"""One-time graph seeding for projects flipped to ``context.mode = graph``.

When ``scaffold._migrate_context_mode`` config-flips a legacy ``hybrid`` (or
mode-less) project to ``graph``, the Markdown under ``docs/`` survives but the
graph store is empty and carries no snapshot — so the first ``context read`` /
``finalize`` would triage every document as NEVER_EXPORTED drift. Seeding
ingests the Markdown into the graph and finalizes it (export baselines +
snapshot), leaving reconcile at zero.

Idempotent: an existing snapshot short-circuits to a skip, so re-running
``upgrade apply`` is a no-op once the first seed has snapshotted the graph.
"""

from __future__ import annotations

import gc
from dataclasses import dataclass
from pathlib import Path

from cataforge.application.context.write import ensure_store, finalize, ingest, reconcile_check
from cataforge.core.paths import KG_SNAPSHOTS_REL
from cataforge.domain.kg._dispatch import context_mode
from cataforge.domain.kg.reconcile import ReconcileReport
from cataforge.domain.kg.snapshot import list_snapshots


@dataclass
class SeedResult:
    """Outcome of a graph migration seed."""

    action: str  # "seeded" | "skipped" | "blocked"
    detail: str


def seed_graph_from_docs(project_root: str) -> SeedResult:
    """Seed an empty graph from the on-disk Markdown after a graph migration.

    Returns ``skipped`` when seeding does not apply (non-graph mode, a snapshot
    already exists, or there are no documents), ``seeded`` when ingest +
    finalize leave reconcile clean, and ``blocked`` when reconcile is non-zero
    afterwards (surfacing the count rather than silently passing).
    """
    root = Path(project_root)
    if context_mode(root) != "graph":
        return SeedResult("skipped", "not graph mode")
    if list_snapshots(root / KG_SNAPSHOTS_REL):
        return SeedResult("skipped", "snapshot present — store hydrates from it")

    # ingest → finalize → reconcile each open the RocksDB store, whose lock is
    # only released on GC; collect between the chained opens so the next one
    # does not hit a held lock (Windows single-process behavior).
    ensure_store(project_root)
    gc.collect()
    stats = ingest(project_root)
    gc.collect()
    doc_count = getattr(stats, "extracted_documents", 0)
    if not (doc_count + getattr(stats, "extracted_entities", 0)):
        return SeedResult("skipped", "no documents to seed")

    finalize(project_root)
    gc.collect()
    report = reconcile_check(project_root)
    gc.collect()
    if report.ok:
        return SeedResult("seeded", f"ingested {doc_count} document(s); reconcile clean")
    drift = report.document_drift_count if isinstance(report, ReconcileReport) else 0
    return SeedResult(
        "blocked",
        f"seeded {doc_count} document(s) but reconcile is non-zero "
        f"({drift} drift) — run `cataforge context reconcile`",
    )
