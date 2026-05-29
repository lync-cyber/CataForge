"""Text rendering for the cross-document consistency report.

Kept separate from ``checker.collect()`` so the check logic stays free of
I/O and the same :class:`CheckReport` can also serialize to JSON.
"""

from __future__ import annotations

from cataforge.runtime.skill.builtins._shared import CheckReport


def render_text(report: CheckReport) -> str:
    """Render a cross-doc :class:`CheckReport` to the human-readable form."""
    if report.summary.get("skipped"):
        return report.headline or ""

    lines: list[str] = [report.headline or "", ""]
    for issue in report.issues:
        lines.append(f"{issue.severity.value}: [{issue.category}] {issue.message}")

    matrix = report.summary.get("matrix") or []
    if matrix:
        lines.append("")
        lines.append("=== 需求追踪矩阵 ===")
        lines.append(
            "| Feature | ACs | ARCH Module | ARCH API "
            "| DEV-PLAN Task | UI-SPEC Page | Coverage |"
        )
        lines.append("|" + "|".join(["---"] * 7) + "|")
        for row in matrix:
            lines.append(
                f"| {row['feature']} | {row['ac_count']} "
                f"| {row['arch_modules']} | {row['arch_apis']} "
                f"| {row['devplan_tasks']} | {row['uispec_pages']} "
                f"| {row['coverage']} |"
            )
        missing_count = sum(1 for r in matrix if r["coverage"] == "missing")
        partial_count = sum(1 for r in matrix if r["coverage"] == "partial")
        if missing_count > 0:
            lines.append("")
            lines.append(
                f"覆盖缺口: {missing_count} missing, {partial_count} partial "
                f"/ {len(matrix)} total"
            )

    lines.append("")
    if report.issues.blocking:
        lines.append(f"CRITICAL/HIGH: {len(report.issues.blocking)} 项")
    elif report.issues.advisory:
        lines.append(f"MEDIUM/LOW: {len(report.issues.advisory)} 项 (无阻塞问题)")
    else:
        lines.append("PASS: 跨文档一致性校验全部通过")
    return "\n".join(lines)
