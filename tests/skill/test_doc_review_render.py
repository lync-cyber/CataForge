"""Render-layer + structured-report tests for the doc-review builtin.

Locks the text output byte-for-byte (no drift from the pre-refactor print
path) and exercises the JSON serialization the structured report enables.
Doc-review gates on blocking findings only, so advisory findings are
reported without failing the document.
"""

from __future__ import annotations

import json

from cataforge.core.types import Severity
from cataforge.runtime.skill.builtins._shared import CheckReport, IssueCollector
from cataforge.runtime.skill.builtins.doc_review._render import render_text

_HEAD = "检查: docs/prd/prd.md (type=prd, volume=main)"


def _report(*, summary=None, issues=()) -> CheckReport:
    collector = IssueCollector()
    for sev, msg in issues:
        collector.add(sev, "doc-structure", msg)
    return CheckReport(collector, summary=summary or {"unknown_doc_type": None}, headline=_HEAD)


def test_render_pass_no_findings() -> None:
    assert render_text(_report()) == f"{_HEAD}\nPASS: 所有检查通过"


def test_render_failures_and_warnings_interleaved_in_order() -> None:
    report = _report(
        issues=(
            (Severity.HIGH, "缺少author字段"),
            (Severity.LOW, "文档行数超过阈值"),
            (Severity.HIGH, "缺少deps字段"),
        )
    )
    assert render_text(report) == (
        f"{_HEAD}\n"
        "FAIL: 缺少author字段\n"
        "WARN: 文档行数超过阈值\n"
        "FAIL: 缺少deps字段\n"
        "WARNINGS: 1\n"
        "TOTAL FAILURES: 2"
    )


def test_render_warnings_only_still_passes() -> None:
    report = _report(issues=((Severity.LOW, "ID编号不连续"),))
    assert render_text(report) == (f"{_HEAD}\nWARN: ID编号不连续\nWARNINGS: 1\nPASS: 所有检查通过")


def test_render_unknown_doc_type_line() -> None:
    report = _report(summary={"unknown_doc_type": "mystery"})
    assert render_text(report) == (
        f"{_HEAD}\nWARN: 未知的文档类型 'mystery'，仅执行通用检查\nPASS: 所有检查通过"
    )


def test_to_dict_serializes_findings() -> None:
    report = _report(issues=((Severity.HIGH, "缺少deps字段"),))
    payload = json.loads(json.dumps(report.to_dict(), ensure_ascii=False))
    assert payload["issues"][0] == {
        "severity": "HIGH",
        "category": "doc-structure",
        "message": "缺少deps字段",
    }
    assert payload["headline"] == _HEAD
