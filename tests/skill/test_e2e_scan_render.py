"""Render-layer + structured-report tests for the e2e-scan builtin.

Locks the text output byte-for-byte (no drift from the pre-refactor print
path). All e2e-scan findings are advisory; the scan never blocks.
"""

from __future__ import annotations

from cataforge.core.types import Severity
from cataforge.runtime.skill.builtins._shared import CheckReport, IssueCollector
from cataforge.runtime.skill.builtins.testing._render import render_text

_RULE = "=" * 50


def _report(*, file_count, backdoor_total, real_input_total, messages=()) -> CheckReport:
    issues = IssueCollector()
    for msg in messages:
        issues.add(Severity.LOW, "e2e_backdoor_scan", msg)
    return CheckReport(
        issues,
        summary={
            "backdoor_total": backdoor_total,
            "real_input_total": real_input_total,
            "file_count": file_count,
        },
        headline=f"e2e_scan: 扫描 {file_count} 个 e2e 文件 @ tests/e2e",
    )


def test_render_clean_with_real_input() -> None:
    report = _report(file_count=3, backdoor_total=0, real_input_total=5)
    assert render_text(report) == (
        "e2e_scan: 扫描 3 个 e2e 文件 @ tests/e2e\n"
        f"{_RULE}\n"
        "\n"
        f"{_RULE}\n"
        "Summary: 0 backdoor WARN, 5 real-input call(s) across 3 file(s)\n"
        "RESULT: PASS"
    )


def test_render_backdoor_findings_tagged_warnings_only() -> None:
    report = _report(
        file_count=1,
        backdoor_total=1,
        real_input_total=2,
        messages=("[a.spec.ts:2] e2e_backdoor_scan (window.__*__): window.__X__ = 1",),
    )
    assert render_text(report) == (
        "e2e_scan: 扫描 1 个 e2e 文件 @ tests/e2e\n"
        f"{_RULE}\n"
        "WARN: [a.spec.ts:2] e2e_backdoor_scan (window.__*__): window.__X__ = 1\n"
        "\n"
        f"{_RULE}\n"
        "Summary: 1 backdoor WARN, 2 real-input call(s) across 1 file(s)\n"
        "RESULT: PASS (warnings only)"
    )


def test_render_zero_real_input_flags_unverified() -> None:
    report = _report(file_count=2, backdoor_total=0, real_input_total=0)
    # No backdoor warnings AND nothing verified: honest wording, not the
    # contradictory "(warnings only)" on a zero-warning run.
    assert render_text(report).endswith("RESULT: PASS (no real-input verified)")
