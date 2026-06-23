"""Feedback collectors — gather local diagnostics into plain dict/list data."""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from cataforge import __version__ as _package_version
from cataforge.application.services.doctor_summary import (
    collect_doctor_summary as collect_doctor_summary,
)
from cataforge.core.config import ConfigManager
from cataforge.core.corrections import CORRECTIONS_LOG_REL
from cataforge.core.errors import ConfigError
from cataforge.core.event_log import EVENT_LOG_REL, MAX_EVENTLOG_BYTES

logger = logging.getLogger("cataforge.feedback")


PACKAGE_VERSION = _package_version


RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT = 3


DEFAULT_EVENT_LOG_TAIL = 20


DOCTOR_TRANSCRIPT_CHAR_CAP = 8000


UPSTREAM_GAP = "upstream-gap"


@dataclass(frozen=True)
class CorrectionEntry:
    """A single CORRECTIONS-LOG entry parsed from the markdown log.

    Fields mirror what ``record_correction`` writes; ``ts`` is the section
    date (YYYY-MM-DD) since the markdown only stores day-precision.
    """

    ts: str
    agent: str
    phase: str
    trigger: str
    question: str
    baseline: str
    actual: str
    deviation: str


@dataclass
class FeedbackPayload:
    """Assembled feedback content; rendered to markdown by ``render_*``."""

    kind: str  # "bug" | "suggest" | "correction-export"
    title: str
    summary: str  # one-paragraph user-supplied summary (or auto-generated)
    environment: dict[str, str] = field(default_factory=dict)
    doctor: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    corrections: list[CorrectionEntry] = field(default_factory=list)
    framework_review: dict[str, Any] = field(default_factory=dict)
    user_notes: str = ""
    # doc_id slug that lands in the rendered YAML front matter; auto-derived
    # from ``title`` when not set. ``doc_type: framework-feedback`` /
    # ``status: approved`` are constants — the front matter exists so
    # ``cataforge docs validate`` accepts a bundle saved via ``--out``.
    doc_id: str = ""


def collect_environment(project_root: Path) -> dict[str, str]:
    """Capture the static env block (no PII)."""
    try:
        data = ConfigManager(project_root).load_raw()
    except (OSError, ValueError, ConfigError):
        data = {}
    scaffold_version = str(data.get("version", "(unknown)"))
    runtime_platform = str((data.get("runtime") or {}).get("platform", "(unknown)"))
    return {
        "package_version": PACKAGE_VERSION,
        "scaffold_version": scaffold_version,
        "python_version": (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
        "platform": platform.platform(),
        "runtime_platform": runtime_platform,
    }


def collect_recent_events(
    project_root: Path,
    *,
    since: str | None = None,
    limit: int = DEFAULT_EVENT_LOG_TAIL,
) -> list[dict[str, Any]]:
    """Return the tail of EVENT-LOG.jsonl, optionally filtered by ts ≥ since.

    ``since`` is parsed loosely: ``YYYY-MM-DD`` works, as does any ISO 8601
    prefix. Malformed lines are skipped silently — the log is best-effort
    observability, not a ledger.
    """
    log = project_root / EVENT_LOG_REL
    if not log.is_file():
        return []
    if log.stat().st_size > MAX_EVENTLOG_BYTES:
        logger.warning(
            "event log exceeds %d bytes; skipping collect_recent_events: %s",
            MAX_EVENTLOG_BYTES,
            log,
        )
        return []
    cutoff = _parse_since(since)
    rows: list[dict[str, Any]] = []
    for raw in log.read_text(errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        if cutoff is not None:
            ts = _parse_ts(rec.get("ts"))
            if ts is None or ts < cutoff:
                continue
        rows.append(rec)
    return rows[-limit:] if limit > 0 else rows


_HEADING_RE = re.compile(
    r"^###\s+(?P<date>\d{4}-\d{2}-\d{2})\s+\|\s+"
    r"(?P<agent>[^|]+?)\s+\|\s+(?P<phase>.+?)\s*$"
)


_FIELD_RE = re.compile(r"^-\s+(?P<key>[^:：]+)[:：]\s*(?P<value>.*?)\s*$")


_FIELD_KEYS = {
    "触发信号": "trigger",
    "问题/假设": "question",
    "基线/推荐": "baseline",
    "实际/选择": "actual",
    "偏差类型": "deviation",
}


_DEVIATION_TOKEN_RE = re.compile(r"[\s(（]")


def _deviation_token(raw: str) -> str:
    """Leading token of a 偏差类型 value, before any inline annotation.

    Hand-written / historical entries annotate the deviation inline, e.g.
    ``upstream-gap (dev-plan 漏 M-002↔M-003 集成点)``. Enum values never
    contain whitespace or parentheses, so the leading token is the
    canonical deviation that filtering and counting compare against.
    """
    return _DEVIATION_TOKEN_RE.split(raw.strip(), maxsplit=1)[0]


def collect_corrections(
    project_root: Path,
    *,
    deviation: str | None = None,
    since: str | None = None,
) -> list[CorrectionEntry]:
    """Parse CORRECTIONS-LOG.md into structured records.

    ``deviation`` filters by the value of the "偏差类型" field; ``None``
    means return everything. ``since`` is a YYYY-MM-DD inclusive lower
    bound on the section heading date.
    """
    log = project_root / CORRECTIONS_LOG_REL
    if not log.is_file():
        return []
    text = log.read_text(errors="replace")
    cutoff = _parse_since_date(since)

    out: list[CorrectionEntry] = []
    current: dict[str, str] = {}
    heading: re.Match[str] | None = None

    def flush() -> None:
        if not heading:
            return
        if cutoff is not None:
            try:
                d = date.fromisoformat(heading.group("date"))
            except ValueError:
                return
            if d < cutoff:
                return
        entry_dev = _deviation_token(current.get("deviation", "preference"))
        if deviation is not None and entry_dev != deviation:
            return
        out.append(
            CorrectionEntry(
                ts=heading.group("date"),
                agent=heading.group("agent").strip(),
                phase=heading.group("phase").strip(),
                trigger=current.get("trigger", ""),
                question=current.get("question", ""),
                baseline=current.get("baseline", ""),
                actual=current.get("actual", ""),
                deviation=entry_dev,
            )
        )

    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            flush()
            heading = m
            current = {}
            continue
        if heading is None:
            continue
        f = _FIELD_RE.match(line)
        if not f:
            continue
        key = f.group("key").strip()
        py_key = _FIELD_KEYS.get(key)
        if py_key is None:
            continue
        current[py_key] = f.group("value").strip()
    flush()
    return out


def collect_framework_review(project_root: Path) -> dict[str, Any]:
    """Best-effort: run ``framework-review`` Layer 1 and capture FAILs.

    Skipped silently when the project has no ``.cataforge/`` (a downstream
    project pre-setup) or when the skill is unreachable. Used by the bug
    report to surface upstream-meta issues the user might not have noticed.
    """
    # Step 1: import — failure here means the skill subsystem isn't
    # importable at all (missing optional dep, broken upstream package).
    # That is genuinely unavailable, not a runtime error.
    try:
        from cataforge.runtime.skill.runner import SkillRunner
    except ImportError as e:
        return {"status": "skipped", "reason": f"runner-unavailable: {e}"}

    if not (project_root / ".cataforge").is_dir():
        return {"status": "skipped", "reason": "no .cataforge/ scaffold"}

    # Step 2: instantiate + run — failure here is a real runtime
    # problem in the skill runner itself (subprocess crash, malformed
    # SKILL.md, etc.). Surface a traceback so the bug report carries
    # enough context to act on, instead of collapsing every cause into
    # a single opaque "runner-failed" line.
    try:
        runner = SkillRunner(project_root=project_root)
        result = runner.run("framework-review", ["all"], agent="feedback-report")
    except Exception as e:
        import traceback as _tb

        return {
            "status": "error",
            "reason": f"runner-failed: {type(e).__name__}: {e}",
            "traceback": _tb.format_exc(),
        }
    fails = [line for line in (result.stdout or "").splitlines() if "FAIL" in line or "✖" in line]
    return {
        "status": "ok",
        "exit_code": result.returncode,
        "fails": fails[:50],  # cap to keep the bundle small
    }


def redact(text: str, project_root: Path, *, include_paths: bool = False) -> str:
    """Replace home + project paths with placeholders unless opted out.

    Order matters: project root usually lives under home, so we replace it
    first to avoid a half-redacted ``~/<rest of project>`` form.
    """
    if include_paths:
        return text
    project = str(project_root)
    home = str(Path.home())
    out = text
    if project:
        out = out.replace(project, "<project>")
    if home and home != project:
        out = out.replace(home, "~")
    # Catch a second-pass leak: WindowsPath repr uses backslashes that may not
    # survive the literal string compare above.
    if os.sep != "/":
        out = out.replace(project.replace(os.sep, "/"), "<project>")
        out = out.replace(home.replace(os.sep, "/"), "~")
    return out


def _parse_since(since: str | None) -> datetime | None:
    if not since:
        return None
    try:
        # Accept date or full ISO timestamp.
        if len(since) == 10:
            return datetime.fromisoformat(since).replace(tzinfo=UTC)
        return datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_since_date(since: str | None) -> date | None:
    if not since:
        return None
    try:
        return date.fromisoformat(since[:10])
    except ValueError:
        return None


def _parse_ts(ts: Any) -> datetime | None:
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def upstream_gap_count(project_root: Path) -> int:
    """Convenience for the skill: how many `upstream-gap` corrections sit
    in the log right now. Returns 0 when the log doesn't exist yet."""
    return len(collect_corrections(project_root, deviation=UPSTREAM_GAP))
