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
    """Correction-log entries as a timeline, one event per correction."""
    events = tuple(
        TimelineEvent(
            ts=e.ts,
            label=f"{e.deviation} · {e.phase}".strip(" ·") or e.deviation,
            category=e.deviation,
        )
        for e in collect_corrections(root)
    )
    return Timeline(events=events, title="correction decay")
