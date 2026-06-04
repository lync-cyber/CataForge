"""Feedback-bundle assembler — turns local diagnostics into upstream-ready markdown.

Split into ``collectors`` (gather), ``renderers`` (format) and ``assemblers``
(compose). This package re-exports the full public surface so callers keep
importing ``cataforge.application.feedback.<name>``.

Privacy: by default every absolute path under ``Path.home()`` / the project
root is redacted; ``include_paths=True`` opts out. Import-safe: no I/O at
import time.
"""

from __future__ import annotations

from cataforge.application.feedback.assemblers import (
    assemble_bug,
    assemble_correction_export,
    assemble_suggestion,
    iter_clipboard_commands,
)
from cataforge.application.feedback.collectors import (
    DEFAULT_EVENT_LOG_TAIL,
    DOCTOR_TRANSCRIPT_CHAR_CAP,
    PACKAGE_VERSION,
    RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT,
    UPSTREAM_GAP,
    CorrectionEntry,
    FeedbackPayload,
    collect_corrections,
    collect_doctor_summary,
    collect_environment,
    collect_framework_review,
    collect_recent_events,
    logger,
    redact,
    upstream_gap_count,
)
from cataforge.application.feedback.renderers import (
    derive_doc_id,
    render_bug_report,
    render_correction_export,
    render_suggestion,
)

__all__ = [
    "DEFAULT_EVENT_LOG_TAIL",
    "DOCTOR_TRANSCRIPT_CHAR_CAP",
    "PACKAGE_VERSION",
    "RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT",
    "UPSTREAM_GAP",
    "CorrectionEntry",
    "FeedbackPayload",
    "collect_corrections",
    "collect_doctor_summary",
    "collect_environment",
    "collect_framework_review",
    "collect_recent_events",
    "logger",
    "redact",
    "upstream_gap_count",
    "derive_doc_id",
    "render_bug_report",
    "render_correction_export",
    "render_suggestion",
    "assemble_bug",
    "assemble_correction_export",
    "assemble_suggestion",
    "iter_clipboard_commands",
]
