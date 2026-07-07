"""Overview KPI snapshots — an append-only JSONL time series.

``append_snapshot`` freezes the current overview points with a timestamp;
``read_snapshots`` loads them back fault-tolerantly: malformed lines are
skipped, every valid record is kept, so one damaged line never hides the
rest of the history (the EVENT-LOG reading discipline).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from cataforge.core.viz.model import MetricSeries

SNAPSHOT_FILENAME = "VIZ-SNAPSHOTS.jsonl"


def snapshot_path(root: Path) -> Path:
    return root / "docs" / SNAPSHOT_FILENAME


def append_snapshot(root: Path) -> Path:
    """Collect the overview series and append it as one JSONL record."""
    from cataforge.application.viz.collectors.overview import collect

    view = collect(root)
    points = [asdict(p) for p in view.points] if isinstance(view, MetricSeries) else []
    rec = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "points": points,
    }
    path = snapshot_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(rec, ensure_ascii=False).encode("utf-8") + b"\n"
    with path.open("ab") as f:
        f.write(line)
    return path


def read_snapshots(root: Path) -> list[dict[str, Any]]:
    """All valid snapshot records in file order; malformed lines skipped."""
    path = snapshot_path(root)
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for raw in path.read_text(errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("points"), list):
            records.append(rec)
    return records
