"""Project-health overview: one MetricSeries aggregating the KPIs the
dashboard strip shows — phase/gate, core-doc completion, Feature coverage,
doc link health, correction decay. Every number comes from an existing data
source; no new data layer.

Each KPI group degrades independently: an unreachable source (no KG, no
doc-index, not a driven project) drops that group's points instead of failing
the whole view, so consumers can render a per-tile "—" fallback. A project
with no reachable source at all yields an empty series (``viz status``
reports it EMPTY, never an error).

Point vocabulary (series / label / value):

* ``phase`` — ``applicable``/0|1 (0 when the instruction file is present but
  the project isn't workflow-driven, e.g. a meta project tracking progress
  outside the SDLC pipeline; the remaining points are then omitted),
  ``current:<当前阶段名>``/1-based sequence index, ``gate_ok``/0|1,
  ``total``/sequence length.
* ``docs`` — one point per core doc_type (from the workflow sequence's
  :data:`~cataforge.core.phases.PHASE_DOC_TYPE`): 0 missing, 0.5 present,
  1 approved. Omitted entirely for a non-driven project (SDLC docs N/A).
* ``coverage`` — ``full`` / ``partial`` / ``none`` Feature counts.
* ``links`` — ``stale`` / ``xref_error`` counts.
* ``decay`` — ``recent_30d`` count plus one point per ``YYYY-MM`` month.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from cataforge.application.feedback.collectors import collect_corrections
from cataforge.application.phase import evaluate_phase
from cataforge.application.viz.collectors._kg import open_kg
from cataforge.application.viz.collectors.process import is_driven, phase_sequence, sdlc_applicable
from cataforge.core.errors import CataforgeError
from cataforge.core.io import read_json
from cataforge.core.phases import PHASE_DOC_TYPE
from cataforge.core.viz.model import MetricPoint, MetricSeries, View
from cataforge.domain.docs.indexer import INDEX_FILENAME, find_stale_deps, find_xref_errors

RECENT_LABEL = "recent_30d"
SELF_CAUSED_LABEL = "self_caused"
CURRENT_PREFIX = "current:"
_RECENT_DAYS = 30


def _phase_points(root: Path) -> list[MetricPoint]:
    current, checks = evaluate_phase(root)
    if not is_driven(current):
        # instruction file present but no workflow phase → SDLC N/A, not a
        # blocked-gate false alarm. The single flag lets the tile show N/A.
        return [MetricPoint(label="applicable", value=0.0, series="phase", unit="flag")]
    sequence = phase_sequence(root)
    index = sequence.index(current) + 1 if current in sequence else 0
    gate_ok = 0.0 if any(not ok for _, ok, _ in checks) else 1.0
    return [
        MetricPoint(label="applicable", value=1.0, series="phase", unit="flag"),
        MetricPoint(
            label=f"{CURRENT_PREFIX}{current}", value=float(index), series="phase", unit="index"
        ),
        MetricPoint(label="gate_ok", value=gate_ok, series="phase", unit="flag"),
        MetricPoint(label="total", value=float(len(sequence)), series="phase", unit="count"),
    ]


def _core_doc_types(sequence: list[str]) -> list[str]:
    """The doc gates along the workflow sequence, in phase order."""
    out: list[str] = []
    for phase in sequence:
        gate = PHASE_DOC_TYPE.get(phase)
        if gate is None:
            continue
        for doc_type in (gate,) if isinstance(gate, str) else gate:
            if doc_type not in out:
                out.append(doc_type)
    return out


def _doc_points(root: Path) -> list[MetricPoint]:
    """docs + links groups; both read the doc-index, absent ⇒ neither. The
    core-doc completion (docs) group is dropped for a non-driven project, whose
    SDLC docs are N/A; the links group stays (any indexed docs can go stale)."""
    index_path = root / "docs" / INDEX_FILENAME
    if not index_path.is_file():
        return []
    documents = read_json(str(index_path)).get("documents") or {}
    statuses: dict[str, list[str]] = {}
    for entry in documents.values() if isinstance(documents, dict) else ():
        if not isinstance(entry, dict):  # tolerate a structurally damaged index
            continue
        doc_type = str(entry.get("doc_type") or "")
        statuses.setdefault(doc_type, []).append(str(entry.get("status") or "draft"))

    points: list[MetricPoint] = []
    if sdlc_applicable(root):
        for doc_type in _core_doc_types(phase_sequence(root)):
            # agile modes gate on the -lite variant of the same doc_type
            found = statuses.get(doc_type, []) + statuses.get(f"{doc_type}-lite", [])
            if not found:
                value = 0.0
            elif "approved" in found:
                value = 1.0
            else:
                value = 0.5
            points.append(MetricPoint(label=doc_type, value=value, series="docs", unit="ratio"))

    root_str = str(root)
    try:  # the indexer's validators assume structurally sound entries
        stale, xref = len(find_stale_deps(root_str)), len(find_xref_errors(root_str))
    except (AttributeError, TypeError, KeyError):
        return points  # damaged index: keep the docs group, drop the links group
    points.append(MetricPoint(label="stale", value=float(stale), series="links", unit="count"))
    points.append(MetricPoint(label="xref_error", value=float(xref), series="links", unit="count"))
    return points


def _coverage_points(root: Path) -> list[MetricPoint]:
    with open_kg(root) as kg:
        rows = kg.trace.bidirectional_coverage()
    full = sum(1 for r in rows if r.has_impl and r.has_test)
    none = sum(1 for r in rows if not r.has_impl and not r.has_test)
    partial = len(rows) - full - none
    return [
        MetricPoint(label="full", value=float(full), series="coverage", unit="count"),
        MetricPoint(label="partial", value=float(partial), series="coverage", unit="count"),
        MetricPoint(label="none", value=float(none), series="coverage", unit="count"),
    ]


def _decay_points(root: Path) -> list[MetricPoint]:
    entries = collect_corrections(root)
    if not entries:
        return []
    cutoff = (datetime.now() - timedelta(days=_RECENT_DAYS)).strftime("%Y-%m-%d")
    recent = sum(1 for e in entries if e.ts >= cutoff)
    # self-caused is the cohort the retrospective gate counts (deviation axis,
    # per the Retrospective Protocol's trigger); preference / upstream-gap /
    # external corrections don't push toward a retro.
    self_caused = sum(1 for e in entries if e.deviation == "self-caused")
    monthly = Counter(e.ts[:7] for e in entries)
    points = [
        MetricPoint(label=RECENT_LABEL, value=float(recent), series="decay", unit="count"),
        MetricPoint(
            label=SELF_CAUSED_LABEL, value=float(self_caused), series="decay", unit="count"
        ),
    ]
    points.extend(
        MetricPoint(label=month, value=float(count), series="decay", unit="count")
        for month, count in sorted(monthly.items())
    )
    return points


def collect(root: Path, /, **_opts: Any) -> View:
    points: list[MetricPoint] = []
    for group in (_phase_points, _doc_points, _coverage_points, _decay_points):
        try:
            points.extend(group(root))
        except CataforgeError:
            continue  # source unreachable — drop the group, keep the rest
    return MetricSeries(points=tuple(points), title="project health overview")
