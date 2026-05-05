"""Feedback-bundle assembler — turns local diagnostics into upstream-ready markdown.

This module is the single source of truth for what a downstream project sends
back to the CataForge upstream. It composes:

* package + scaffold version, Python, OS, runtime platform
* recent ``cataforge doctor`` summary (FAIL/WARN lines only by default)
* recent EVENT-LOG entries (filtered by ``since`` / ``limit``)
* CORRECTIONS-LOG entries with ``deviation=upstream-gap``
  (the on-correction signal that the upstream baseline itself was wrong)
* optional ``framework-review`` Layer 1 FAIL summary

Privacy: by default every absolute path that lives under ``Path.home()`` or
under the project root is redacted to ``~`` / ``<project>`` so a body pasted
into a public GitHub issue does not leak the user's directory layout.
``include_paths=True`` opts out (used by the test e2e flow).

The module is import-safe: no I/O happens at import time, and every collector
returns a plain dict / list so it can be JSON-serialised by the CLI for
``--out`` mode.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from cataforge import __version__ as _package_version
from cataforge.core.corrections import CORRECTIONS_LOG_REL
from cataforge.core.event_log import EVENT_LOG_REL

PACKAGE_VERSION = _package_version

# Threshold above which `feedback correction-export` will tell the user
# "you have N upstream-gap corrections — consider opening an issue". Mirrors
# RETRO_TRIGGER_SELF_CAUSED in spirit but for the upstream channel; lower
# default since upstream-gap is a stronger signal than self-caused drift.
RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT = 3

# How many recent EVENT-LOG entries land in a bug bundle by default.
DEFAULT_EVENT_LOG_TAIL = 20

# Cap doctor output to keep the rendered body within GitHub's 65k-char limit
# even on very noisy projects (deploy_provenance + hook errors can each run
# 50+ lines). Truncation is only applied to the FAIL/WARN slice — the full
# transcript is preserved in `payload["doctor"]["full"]`.
DOCTOR_TRANSCRIPT_CHAR_CAP = 8000

UPSTREAM_GAP = "upstream-gap"


# ─── data carriers ────────────────────────────────────────────────────────────


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


# ─── environment ──────────────────────────────────────────────────────────────


def collect_environment(project_root: Path) -> dict[str, str]:
    """Capture the static env block (no PII)."""
    runtime_platform = "(unknown)"
    scaffold_version = "(unknown)"
    fw = project_root / ".cataforge" / "framework.json"
    if fw.is_file():
        try:
            data = json.loads(fw.read_text(encoding="utf-8"))
            scaffold_version = str(data.get("version", "(unknown)"))
            runtime_platform = str(
                (data.get("runtime") or {}).get("platform", "(unknown)")
            )
        except (OSError, ValueError):
            pass
    return {
        "package_version": PACKAGE_VERSION,
        "scaffold_version": scaffold_version,
        "python_version": (
            f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        ),
        "platform": platform.platform(),
        "runtime_platform": runtime_platform,
    }


# ─── doctor summary ───────────────────────────────────────────────────────────

_DOCTOR_FAIL_RE = re.compile(r"^\s*(?:FAIL|✖|ERROR|missing|MISSING)\b", re.MULTILINE)
_DOCTOR_WARN_RE = re.compile(r"^\s*(?:WARN|⚠)\b", re.MULTILINE)


def collect_doctor_summary(project_root: Path) -> dict[str, Any]:
    """Run ``cataforge doctor`` in-process and extract failure/warning lines.

    Uses Click's ``CliRunner`` rather than spawning a subprocess so the call
    stays fast (no fork) and so unit tests can stub the project root without
    PATH gymnastics. Failures inside doctor are captured but never raised —
    the assembler should always be able to produce a partial bundle.
    """
    out = {"exit_code": -1, "fails": [], "warns": [], "full": ""}
    try:
        from click.testing import CliRunner

        from cataforge.cli.main import cli
    except Exception as e:
        out["fails"] = [f"(could not import doctor: {e})"]
        return out

    # ``mix_stderr`` was the default on Click ≤ 8.1 and was removed as a
    # constructor kwarg in 8.2 (now controlled via ``invoke(..., catch_exceptions)``).
    # We fall back to the keyword-less constructor so we work across both;
    # output capture mixes stderr+stdout either way under our pinned floor.
    try:
        runner = CliRunner(mix_stderr=True)  # type: ignore[call-arg]
    except TypeError:
        runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--project-dir", str(project_root), "doctor"],
        catch_exceptions=True,
    )
    text = result.output or ""
    out["exit_code"] = result.exit_code
    out["full"] = text
    out["fails"] = _DOCTOR_FAIL_RE.findall(text) and [
        line for line in text.splitlines() if _DOCTOR_FAIL_RE.match(line)
    ] or []
    out["warns"] = [line for line in text.splitlines() if _DOCTOR_WARN_RE.match(line)]
    return out


# ─── event log tail ───────────────────────────────────────────────────────────


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
    cutoff = _parse_since(since)
    rows: list[dict[str, Any]] = []
    for raw in log.read_text(encoding="utf-8").splitlines():
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


# ─── corrections aggregator ───────────────────────────────────────────────────

# Each correction is rendered as a 6-line block under a `### YYYY-MM-DD | agent | phase`
# heading. The parser is lenient — extra fields between the known six are kept
# but ignored.
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
    text = log.read_text(encoding="utf-8")
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
        entry_dev = current.get("deviation", "preference")
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


# ─── framework-review summary ─────────────────────────────────────────────────


def collect_framework_review(project_root: Path) -> dict[str, Any]:
    """Best-effort: run ``framework-review`` Layer 1 and capture FAILs.

    Skipped silently when the project has no ``.cataforge/`` (a downstream
    project pre-setup) or when the skill is unreachable. Used by the bug
    report to surface upstream-meta issues the user might not have noticed.
    """
    try:
        from cataforge.skill.runner import SkillRunner
    except Exception as e:
        return {"status": "skipped", "reason": f"runner-import-failed: {e}"}
    if not (project_root / ".cataforge").is_dir():
        return {"status": "skipped", "reason": "no .cataforge/ scaffold"}
    try:
        runner = SkillRunner(project_root=project_root)
        result = runner.run("framework-review", ["all"], agent="feedback-report")
    except Exception as e:
        return {"status": "skipped", "reason": f"runner-failed: {e}"}
    fails = [
        line
        for line in (result.stdout or "").splitlines()
        if "FAIL" in line or "✖" in line
    ]
    return {
        "status": "ok",
        "exit_code": result.returncode,
        "fails": fails[:50],  # cap to keep the bundle small
    }


# ─── redaction ────────────────────────────────────────────────────────────────


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


# ─── markdown renderers ───────────────────────────────────────────────────────


def _render_environment(env: dict[str, str]) -> str:
    return (
        "## Environment\n\n"
        f"- **CataForge package**: `{env.get('package_version', '?')}`\n"
        f"- **Scaffold version**: `{env.get('scaffold_version', '?')}`\n"
        f"- **Python**: `{env.get('python_version', '?')}`\n"
        f"- **Platform**: `{env.get('platform', '?')}`\n"
        f"- **Runtime platform**: `{env.get('runtime_platform', '?')}`\n"
    )


def _render_doctor(doctor: dict[str, Any]) -> str:
    if not doctor:
        return ""
    fails = doctor.get("fails") or []
    warns = doctor.get("warns") or []
    full = doctor.get("full") or ""
    if len(full) > DOCTOR_TRANSCRIPT_CHAR_CAP:
        full = (
            full[:DOCTOR_TRANSCRIPT_CHAR_CAP]
            + f"\n... [truncated — full transcript was {len(full)} chars]"
        )
    out = ["## `cataforge doctor` summary\n"]
    out.append(f"- **Exit code**: `{doctor.get('exit_code', '?')}`")
    out.append(f"- **Failing checks**: `{len(fails)}`")
    out.append(f"- **Warnings**: `{len(warns)}`\n")
    if fails:
        out.append("### Failing lines\n")
        out.append("```")
        out.extend(fails[:30])
        out.append("```\n")
    if warns:
        out.append("### Warning lines\n")
        out.append("```")
        out.extend(warns[:30])
        out.append("```\n")
    out.append("<details><summary>Full doctor transcript</summary>\n")
    out.append("```")
    out.append(full or "(empty)")
    out.append("```\n</details>\n")
    return "\n".join(out)


def _render_events(events: list[dict[str, Any]]) -> str:
    if not events:
        return ""
    out = [f"## Recent EVENT-LOG (last {len(events)})\n"]
    out.append("```jsonl")
    for rec in events:
        out.append(json.dumps(rec, ensure_ascii=False))
    out.append("```\n")
    return "\n".join(out)


def _render_corrections(corrections: list[CorrectionEntry], *, header: str) -> str:
    if not corrections:
        return ""
    out = [f"## {header} ({len(corrections)})\n"]
    for c in corrections:
        out.append(f"### {c.ts} | {c.agent} | {c.phase}")
        out.append(f"- **Trigger**: `{c.trigger}`")
        out.append(f"- **Deviation**: `{c.deviation}`")
        out.append(f"- **Question**: {c.question}")
        out.append(f"- **Upstream baseline**: {c.baseline}")
        out.append(f"- **Local choice**: {c.actual}")
        out.append("")
    return "\n".join(out)


def _render_framework_review(fr: dict[str, Any]) -> str:
    if not fr:
        return ""
    if fr.get("status") == "skipped":
        return (
            "## `framework-review` summary\n\n"
            f"_Skipped: {fr.get('reason', 'unknown')}._\n"
        )
    fails = fr.get("fails") or []
    out = ["## `framework-review` summary\n"]
    out.append(f"- **Exit code**: `{fr.get('exit_code', '?')}`")
    out.append(f"- **FAIL lines**: `{len(fails)}`\n")
    if fails:
        out.append("```")
        out.extend(fails[:30])
        out.append("```\n")
    return "\n".join(out)


def _render_header(payload: FeedbackPayload) -> str:
    return (
        f"<!-- generated by `cataforge feedback {payload.kind}` "
        f"at {datetime.now(timezone.utc).replace(microsecond=0).isoformat()} -->\n\n"
        f"# {payload.title}\n\n"
        f"## Summary\n\n{payload.summary}\n\n"
    )


def render_bug_report(payload: FeedbackPayload) -> str:
    return (
        _render_header(payload)
        + _render_environment(payload.environment)
        + "\n"
        + _render_doctor(payload.doctor)
        + "\n"
        + _render_framework_review(payload.framework_review)
        + "\n"
        + _render_events(payload.events)
        + "\n"
        + _render_corrections(
            payload.corrections,
            header="On-correction signals (`upstream-gap`)",
        )
        + (
            f"\n## Additional notes\n\n{payload.user_notes}\n"
            if payload.user_notes
            else ""
        )
    )


def render_suggestion(payload: FeedbackPayload) -> str:
    return (
        _render_header(payload)
        + _render_environment(payload.environment)
        + (
            f"\n## Proposal\n\n{payload.user_notes}\n"
            if payload.user_notes
            else "\n## Proposal\n\n_(describe the proposed change here)_\n"
        )
        + "\n"
        + _render_corrections(
            payload.corrections,
            header="Related on-correction signals (`upstream-gap`)",
        )
    )


def render_correction_export(payload: FeedbackPayload) -> str:
    return (
        _render_header(payload)
        + _render_environment(payload.environment)
        + "\n"
        + _render_corrections(
            payload.corrections,
            header="Aggregated `upstream-gap` corrections",
        )
        + (
            f"\n## Additional notes\n\n{payload.user_notes}\n"
            if payload.user_notes
            else ""
        )
    )


# ─── high-level assemblers (called by both CLI and skill) ─────────────────────


def assemble_bug(
    project_root: Path,
    *,
    title: str,
    summary: str,
    user_notes: str = "",
    event_limit: int = DEFAULT_EVENT_LOG_TAIL,
    since: str | None = None,
    include_paths: bool = False,
    skip_framework_review: bool = False,
) -> tuple[FeedbackPayload, str]:
    """Build a bug-report payload and its rendered markdown body."""
    env = collect_environment(project_root)
    doctor = collect_doctor_summary(project_root)
    events = collect_recent_events(project_root, since=since, limit=event_limit)
    corrections = collect_corrections(
        project_root, deviation=UPSTREAM_GAP, since=since
    )
    fr = (
        {"status": "skipped", "reason": "skipped by caller"}
        if skip_framework_review
        else collect_framework_review(project_root)
    )
    payload = FeedbackPayload(
        kind="bug",
        title=title,
        summary=summary,
        environment=env,
        doctor=doctor,
        events=events,
        corrections=list(corrections),
        framework_review=fr,
        user_notes=user_notes,
    )
    body = render_bug_report(payload)
    return payload, redact(body, project_root, include_paths=include_paths)


def assemble_suggestion(
    project_root: Path,
    *,
    title: str,
    summary: str,
    user_notes: str = "",
    include_paths: bool = False,
) -> tuple[FeedbackPayload, str]:
    env = collect_environment(project_root)
    corrections = collect_corrections(project_root, deviation=UPSTREAM_GAP)
    payload = FeedbackPayload(
        kind="suggest",
        title=title,
        summary=summary,
        environment=env,
        corrections=list(corrections),
        user_notes=user_notes,
    )
    body = render_suggestion(payload)
    return payload, redact(body, project_root, include_paths=include_paths)


def assemble_correction_export(
    project_root: Path,
    *,
    title: str,
    summary: str,
    since: str | None = None,
    user_notes: str = "",
    include_paths: bool = False,
) -> tuple[FeedbackPayload, str]:
    env = collect_environment(project_root)
    corrections = collect_corrections(
        project_root, deviation=UPSTREAM_GAP, since=since
    )
    payload = FeedbackPayload(
        kind="correction-export",
        title=title,
        summary=summary,
        environment=env,
        corrections=list(corrections),
        user_notes=user_notes,
    )
    body = render_correction_export(payload)
    return payload, redact(body, project_root, include_paths=include_paths)


# ─── helpers ──────────────────────────────────────────────────────────────────


def _parse_since(since: str | None) -> datetime | None:
    if not since:
        return None
    try:
        # Accept date or full ISO timestamp.
        if len(since) == 10:
            return datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
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


def iter_clipboard_commands() -> Iterable[list[str]]:
    """Best-effort cross-platform clipboard tool list. Caller picks the
    first one that resolves on PATH and pipes the body to stdin."""
    yield ["pbcopy"]            # macOS
    yield ["wl-copy"]           # Wayland
    yield ["xclip", "-selection", "clipboard"]
    yield ["xsel", "--clipboard", "--input"]
    yield ["clip.exe"]          # WSL → Windows
    yield ["clip"]              # native Windows
