"""Decay view: CORRECTIONS-LOG entries as a timeline.

Reuses :func:`collect_corrections`; each correction becomes a dated event
labelled by deviation type + phase. The aggregated count/trend (MetricSeries)
form is a tier-2 (ECharts) concern.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cataforge.application.feedback.collectors import collect_corrections
from cataforge.core.viz.model import Timeline, TimelineEvent, View


def collect_decay(root: Path, /, **_opts: Any) -> View:
    """Correction-log entries as a timeline; identical (date, label) entries
    fold into one event with a ``count``."""
    counts: dict[tuple[str, str, str], int] = {}
    for e in collect_corrections(root):
        label = f"{e.deviation} · {e.phase}".strip(" ·") or e.deviation
        key = (e.ts, e.deviation, label)
        counts[key] = counts.get(key, 0) + 1
    events = tuple(
        TimelineEvent(ts=ts, label=label, category=deviation, count=n)
        for (ts, deviation, label), n in counts.items()
    )
    return Timeline(events=events, title="correction decay")
