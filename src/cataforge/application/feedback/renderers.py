"""Feedback renderers — turn collected data + payload into markdown."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from cataforge.application.feedback.collectors import (
    DOCTOR_TRANSCRIPT_CHAR_CAP,
    CorrectionEntry,
    FeedbackPayload,
)


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
        return f"## `framework-review` summary\n\n_Skipped: {fr.get('reason', 'unknown')}._\n"
    fails = fr.get("fails") or []
    out = ["## `framework-review` summary\n"]
    out.append(f"- **Exit code**: `{fr.get('exit_code', '?')}`")
    out.append(f"- **FAIL lines**: `{len(fails)}`\n")
    if fails:
        out.append("```")
        out.extend(fails[:30])
        out.append("```\n")
    return "\n".join(out)


_DOC_ID_INVALID_CHARS_RE = re.compile(r"[^\w-]+")


_DOC_ID_COLLAPSE_HYPHEN_RE = re.compile(r"-{2,}")


_DOC_ID_MAX_BASE_LEN = 80


def derive_doc_id(title: str, *, kind: str) -> str:
    """Slugify a feedback title into a ``DOC_ID_RE`` (``^[\\w-]+$``) compatible id.

    The CLI uses this when the caller does not pre-supply ``doc_id`` on the
    payload. The title is folded to ASCII (non-ASCII chars dropped — ids must
    stay portable across filesystems and URL anchors), non-word chars become
    hyphens, hyphen runs collapse, and the result is capped at a hyphen
    boundary. Prefixed with ``feedback-<kind>-`` to keep the namespace flat —
    this way two bundles with similar titles still differ by ``kind``. Falls
    back to a date stamp when the title slugifies to nothing.
    """
    base = title.strip().lower().encode("ascii", "ignore").decode("ascii")
    base = _DOC_ID_INVALID_CHARS_RE.sub("-", base)
    base = _DOC_ID_COLLAPSE_HYPHEN_RE.sub("-", base).strip("-")
    # Strip stray "feedback-" / "{kind}-" so titles like "feedback: bar" or
    # "bug: bar" don't end up double-prefixed when we re-prepend below.
    if base.startswith("feedback-"):
        base = base[len("feedback-") :]
    if base.startswith(f"{kind}-"):
        base = base[len(kind) + 1 :]
    if len(base) > _DOC_ID_MAX_BASE_LEN:
        base = base[:_DOC_ID_MAX_BASE_LEN]
        if "-" in base:
            base = base.rsplit("-", 1)[0]
        base = base.strip("-")
    if not base:
        base = datetime.now(UTC).strftime("%Y%m%d")
    return f"feedback-{kind}-{base}"


def _render_frontmatter(payload: FeedbackPayload) -> str:
    """YAML front matter so ``cataforge docs validate`` accepts the bundle.

    Required by issue #115 P5: ``--out`` mode lands the body in a project's
    ``docs/feedback/`` directory and the doc indexer trips an orphan FAIL if
    the file lacks ``doc_type`` + ``status``. ``status: approved`` reflects
    that the user is sending this bundle deliberately (not draft); ``deps:
    []`` keeps it standalone — the bundle is self-contained context for an
    upstream maintainer.
    """
    doc_id = payload.doc_id or derive_doc_id(payload.title, kind=payload.kind)
    return f"---\nid: {doc_id}\ndoc_type: framework-feedback\nstatus: approved\ndeps: []\n---\n\n"


def _render_header(payload: FeedbackPayload) -> str:
    return (
        _render_frontmatter(payload) + f"<!-- generated by `cataforge feedback {payload.kind}` "
        f"at {datetime.now(UTC).replace(microsecond=0).isoformat()} -->\n\n"
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
        + (f"\n## Additional notes\n\n{payload.user_notes}\n" if payload.user_notes else "")
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
        + (f"\n## Additional notes\n\n{payload.user_notes}\n" if payload.user_notes else "")
    )
