"""Text rendering for the e2e scan report.

Kept separate from ``collect()`` so the scan logic stays free of I/O and
the same :class:`CheckReport` can also serialize to JSON.
"""

from __future__ import annotations

from cataforge.runtime.skill.builtins._shared import CheckReport

_RULE = "=" * 50


def render_text(report: CheckReport) -> str:
    """Render an e2e-scan :class:`CheckReport` to the human-readable form.

    All findings are advisory (WARN); the scan never blocks, so the trailing
    RESULT line is always PASS, optionally tagged ``(warnings only)``.
    """
    s = report.summary
    lines: list[str] = [report.headline or "", _RULE]
    for issue in report.issues:
        lines.append(f"WARN: {issue.message}")
    lines.append("")
    lines.append(_RULE)
    lines.append(
        f"Summary: {s['backdoor_total']} backdoor WARN, "
        f"{s['real_input_total']} real-input call(s) across {s['file_count']} file(s)"
    )
    if s["backdoor_total"]:
        note = " (warnings only)"
    elif not s["real_input_total"]:
        # Clean of backdoors but nothing positively verified — say so plainly
        # rather than mislabel a zero-warning run as "warnings only".
        note = " (no real-input verified)"
    else:
        note = ""
    lines.append("RESULT: PASS" + note)
    return "\n".join(lines)
