"""Feedback assemblers — compose collectors + renderers into ready bundles."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from cataforge.application.feedback.collectors import (
    DEFAULT_EVENT_LOG_TAIL,
    UPSTREAM_GAP,
    FeedbackPayload,
    collect_corrections,
    collect_doctor_summary,
    collect_environment,
    collect_framework_review,
    collect_recent_events,
    redact,
)
from cataforge.application.feedback.renderers import (
    render_bug_report,
    render_correction_export,
    render_suggestion,
)


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
    corrections = collect_corrections(project_root, deviation=UPSTREAM_GAP, since=since)
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
    corrections = collect_corrections(project_root, deviation=UPSTREAM_GAP, since=since)
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


def iter_clipboard_commands() -> Iterable[list[str]]:
    """Best-effort cross-platform clipboard tool list. Caller picks the
    first one that resolves on PATH and pipes the body to stdin."""
    yield ["pbcopy"]  # macOS
    yield ["wl-copy"]  # Wayland
    yield ["xclip", "-selection", "clipboard"]
    yield ["xsel", "--clipboard", "--input"]
    yield ["clip.exe"]  # WSL → Windows
    yield ["clip"]  # native Windows
