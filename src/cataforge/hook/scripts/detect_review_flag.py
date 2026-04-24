"""PostToolUse Hook: Capture review-flag corrections from reviewer output.

Matcher: Agent (with matcher_agent_id=[reviewer] in hooks.yaml).
Fires when a CRITICAL/HIGH issue body references an ``[ASSUMPTION]``.
Report shape per COMMON-RULES §审查报告规范.
Never blocks (exit 0).
"""

from __future__ import annotations

import re
import sys
from typing import Any

from cataforge.core.corrections import record_correction
from cataforge.core.paths import find_project_root
from cataforge.hook.base import (
    hook_main,
    matches_capability,
    matches_script_filters,
    read_hook_input,
)

_ISSUE_RE = re.compile(
    r"^###\s*\[(R-\d+)\]\s+(CRITICAL|HIGH|MEDIUM|LOW)\s*[:：]\s*(.+?)\s*$",
    re.MULTILINE,
)
_ROOT_CAUSE_RE = re.compile(
    r"^\s*-\s*\*\*root_cause\*\*\s*[:：]\s*([\w-]+)", re.MULTILINE
)
_ASSUMPTION_TOKEN = "[ASSUMPTION]"


def _split_issues(text: str) -> list[tuple[str, str, str, str]]:
    """Return ``(ref, severity, title, body)`` per issue header in *text*."""
    matches = list(_ISSUE_RE.finditer(text))
    out: list[tuple[str, str, str, str]] = []
    for i, m in enumerate(matches):
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append(
            (m.group(1), m.group(2).upper(), m.group(3).strip(), text[body_start:body_end])
        )
    return out


def _extract_root_cause(body: str) -> str:
    m = _ROOT_CAUSE_RE.search(body)
    return m.group(1).strip().lower() if m else ""


def _resolve_phase(data: dict[str, Any]) -> str:
    phase = data.get("phase") or (data.get("tool_input") or {}).get("phase")
    return str(phase) if phase else "review"


@hook_main
def main() -> None:
    data = read_hook_input()

    if not data or not matches_capability(data, "agent_dispatch"):
        sys.exit(0)

    if not matches_script_filters(data, "detect_review_flag"):
        sys.exit(0)

    result = data.get("tool_response") or data.get("tool_result") or data.get("result")
    if not result:
        sys.exit(0)

    text = str(result)
    if _ASSUMPTION_TOKEN not in text:
        sys.exit(0)

    issues = _split_issues(text)
    if not issues:
        sys.exit(0)

    project_root = find_project_root()
    phase = _resolve_phase(data)
    upstream_agent = (
        (data.get("tool_input") or {}).get("subagent_type")
        or (data.get("tool_input") or {}).get("agent")
        or "unknown-agent"
    )

    written = 0
    for ref, severity, title, body in issues:
        if severity not in ("CRITICAL", "HIGH"):
            continue
        if _ASSUMPTION_TOKEN not in body:
            continue
        root_cause = _extract_root_cause(body) or "self-caused"

        try:
            record_correction(
                project_root,
                trigger="review-flag",
                agent=str(upstream_agent),
                phase=phase,
                question=f"[{ref}] {title}",
                baseline="(reviewer-flagged assumption — see review report)",
                actual=body.strip().splitlines()[0][:200] if body.strip() else "",
                deviation=(
                    root_cause
                    if root_cause in {"self-caused", "external"}
                    else "self-caused"
                ),
            )
            written += 1
        except (ValueError, OSError) as e:
            print(f"[HOOK-WARN] review-flag write failed for {ref}: {e}", file=sys.stderr)

    if written:
        print(
            f"[HOOK-INFO] correction | review-flag | {written} CRITICAL/HIGH "
            f"assumption(s) recorded from {upstream_agent}",
            file=sys.stderr,
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
