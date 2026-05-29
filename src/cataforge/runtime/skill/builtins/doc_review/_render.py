"""Text rendering for the single-document review report.

Kept separate from ``DocChecker.collect()`` so the check logic stays free
of I/O and the same :class:`CheckReport` can also serialize to JSON.
"""

from __future__ import annotations

from cataforge.runtime.skill.builtins._shared import CheckReport


def render_text(report: CheckReport) -> str:
    """Render a doc-review :class:`CheckReport` to the human-readable form.

    Doc-review gates on blocking findings only (advisory findings are
    reported but do not fail the document), so the trailing summary mirrors
    that 0/1 contract rather than the graded CheckReport.exit_code.
    """
    lines: list[str] = [report.headline or ""]
    for issue in report.issues:
        prefix = "FAIL" if issue.blocking else "WARN"
        lines.append(f"{prefix}: {issue.message}")

    unknown = report.summary.get("unknown_doc_type")
    if unknown:
        lines.append(f"WARN: 未知的文档类型 '{unknown}'，仅执行通用检查")

    if report.issues.advisory:
        lines.append(f"WARNINGS: {len(report.issues.advisory)}")
    if not report.issues.blocking:
        lines.append("PASS: 所有检查通过")
    else:
        lines.append(f"TOTAL FAILURES: {len(report.issues.blocking)}")
    return "\n".join(lines)
