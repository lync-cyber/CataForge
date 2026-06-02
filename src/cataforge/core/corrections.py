"""Shared writer for On-Correction Learning Protocol entries.

Every trigger path (option-override / interrupt-override / review-flag)
goes through :func:`record_correction`, which dual-writes to
``docs/reviews/CORRECTIONS-LOG.md`` (human) and
``docs/EVENT-LOG.jsonl`` with ``event=correction`` (machine).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cataforge.core.event_log import EventLogError, append_event, build_record
from cataforge.utils.atomic_write import atomic_write_text

logger = logging.getLogger("cataforge.corrections")

CORRECTIONS_LOG_REL = Path("docs") / "reviews" / "CORRECTIONS-LOG.md"

TriggerSignal = Literal["option-override", "interrupt-override", "review-flag"]
# ``upstream-gap``: the upstream CataForge baseline itself was
# wrong / missing for this project's context. Distinct from ``framework-bug``
# (CataForge framework defect) and ``self-caused`` (downstream drift). The
# ``framework-feedback`` skill aggregates these into an upstream-bound
# issue draft via ``cataforge feedback correction-export``.
DeviationType = Literal["preference", "self-caused", "external", "framework-bug", "upstream-gap"]

VALID_TRIGGERS: frozenset[str] = frozenset({"option-override", "interrupt-override", "review-flag"})
VALID_DEVIATIONS: frozenset[str] = frozenset(
    {"preference", "self-caused", "external", "framework-bug", "upstream-gap"}
)

_HEADER = (
    "---\n"
    'id: "corrections-log"\n'
    "doc_type: correction-log\n"
    "author: cataforge\n"
    "status: approved\n"
    "deps: []\n"
    "---\n"
    "# Corrections Log\n\n"
    "> 由 CataForge 自动追加。On-Correction Learning Protocol 触发条件见\n"
    "> `.cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md`。\n"
)


def record_correction(
    project_root: Path,
    *,
    trigger: str,
    agent: str,
    phase: str,
    question: str,
    baseline: str,
    actual: str,
    deviation: str = "preference",
    write_event_log: bool = True,
) -> dict[str, Path | None]:
    """Append a correction record to CORRECTIONS-LOG.md and EVENT-LOG.jsonl.

    Returns ``{"corrections_log": Path, "event_log": Path | None}``.
    Markdown write is authoritative; EVENT-LOG failures are logged and
    swallowed so a schema error never drops the human-facing entry.
    """
    if trigger not in VALID_TRIGGERS:
        raise ValueError(f"trigger={trigger!r} not in {sorted(VALID_TRIGGERS)}")
    if deviation not in VALID_DEVIATIONS:
        raise ValueError(f"deviation={deviation!r} not in {sorted(VALID_DEVIATIONS)}")

    md_path = _append_markdown(
        project_root,
        trigger=trigger,
        agent=agent,
        phase=phase,
        question=question,
        baseline=baseline,
        actual=actual,
        deviation=deviation,
    )

    event_path: Path | None = None
    if write_event_log:
        try:
            record = build_record(
                event="correction",
                phase=phase,
                detail=f"{trigger}: {question[:80]}",
                agent=agent,
            )
            event_path = append_event(project_root, record)
        except (EventLogError, OSError) as e:
            logger.warning("EVENT-LOG correction write failed: %s", e)

    return {"corrections_log": md_path, "event_log": event_path}


def _append_markdown(
    project_root: Path,
    *,
    trigger: str,
    agent: str,
    phase: str,
    question: str,
    baseline: str,
    actual: str,
    deviation: str,
) -> Path:
    log_path = project_root / CORRECTIONS_LOG_REL
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # UTC to match EVENT-LOG entries — naive local time would let a
    # CST-evening correction land on a different markdown date than the
    # paired EVENT-LOG row, breaking grep-by-date forensics.
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n### {date} | {agent} | {phase}\n"
        f"- 触发信号: {trigger}\n"
        f"- 问题/假设: {question}\n"
        f"- 基线/推荐: {baseline}\n"
        f"- 实际/选择: {actual}\n"
        f"- 偏差类型: {deviation}\n"
    )

    # Read-modify-write through ``atomic_write_text`` so a crash never
    # leaves the file in a header-only / half-entry state. The previous
    # two-branch shape (truncating ``"w"`` for first call, separate
    # ``"a"`` for follow-ups) had two distinct mid-write failure modes:
    # (1) interruption between header write and entry write leaving an
    # entry-less header; (2) two appenders racing each other on a
    # non-atomic ``"a"`` open. CORRECTIONS-LOG grows by one short entry
    # per correction event (a handful per project lifetime), so the
    # read-pre-write I/O overhead is negligible compared to the
    # consistency guarantee.
    existing = log_path.read_text() if log_path.is_file() else _HEADER
    atomic_write_text(log_path, existing + entry)
    return log_path
