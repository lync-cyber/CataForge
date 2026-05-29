"""Render-layer + structured-report tests for the doc-consistency builtin.

Locks the text output byte-for-byte (no drift from the pre-refactor print
path) and exercises the JSON serialization the structured report enables.
"""

from __future__ import annotations

import json

import pytest

from cataforge.core.types import Severity
from cataforge.runtime.skill.builtins._shared import CheckReport, IssueCollector
from cataforge.runtime.skill.builtins.doc_consistency._render import render_text


def _report(*, headline: str, summary: dict, severities=()) -> CheckReport:
    issues = IssueCollector()
    for i, sev in enumerate(severities):
        issues.add(sev, "ac-coverage", f"msg-{i}")
    return CheckReport(issues, summary=summary, headline=headline)


def test_render_skip_is_headline_only() -> None:
    report = _report(
        headline="跳过: 仅发现 1 个文档类型，跨文档校验需要至少 2 个",
        summary={"available": ["prd"], "skipped": True},
    )
    assert render_text(report) == "跳过: 仅发现 1 个文档类型，跨文档校验需要至少 2 个"


def test_render_pass_no_matrix() -> None:
    report = _report(headline="跨文档一致性校验: 发现 prd, arch", summary={"matrix": []})
    assert render_text(report) == (
        "跨文档一致性校验: 发现 prd, arch\n"
        "\n"
        "\n"
        "PASS: 跨文档一致性校验全部通过"
    )


def test_render_blocking_with_matrix_and_coverage_gap() -> None:
    matrix = [
        {
            "feature": "F-001",
            "ac_count": 1,
            "arch_modules": "M-001",
            "arch_apis": "API-001",
            "devplan_tasks": "-",
            "uispec_pages": "-",
            "coverage": "missing",
        }
    ]
    report = _report(
        headline="跨文档一致性校验: 发现 prd, arch",
        summary={"matrix": matrix},
        severities=(Severity.CRITICAL,),
    )
    assert render_text(report) == (
        "跨文档一致性校验: 发现 prd, arch\n"
        "\n"
        "CRITICAL: [ac-coverage] msg-0\n"
        "\n"
        "=== 需求追踪矩阵 ===\n"
        "| Feature | ACs | ARCH Module | ARCH API | DEV-PLAN Task | UI-SPEC Page | Coverage |\n"
        "|---|---|---|---|---|---|---|\n"
        "| F-001 | 1 | M-001 | API-001 | - | - | missing |\n"
        "\n"
        "覆盖缺口: 1 missing, 0 partial / 1 total\n"
        "\n"
        "CRITICAL/HIGH: 1 项"
    )


def test_render_advisory_only() -> None:
    report = _report(
        headline="跨文档一致性校验: 发现 prd, ui-spec",
        summary={"matrix": []},
        severities=(Severity.MEDIUM,),
    )
    assert render_text(report).endswith("MEDIUM/LOW: 1 项 (无阻塞问题)")


def test_to_dict_round_trips_through_json() -> None:
    report = _report(
        headline="跨文档一致性校验: 发现 prd, arch",
        summary={"available": ["prd", "arch"], "matrix": []},
        severities=(Severity.HIGH,),
    )
    payload = json.loads(json.dumps(report.to_dict(), ensure_ascii=False))
    assert payload["exit_code"] == 1
    assert payload["issues"][0]["severity"] == "HIGH"
    assert payload["summary"]["available"] == ["prd", "arch"]
    assert payload["headline"].startswith("跨文档一致性校验")


@pytest.mark.parametrize(
    ("severities", "expected"),
    [
        ((), 0),
        ((Severity.LOW,), 2),
        ((Severity.LOW, Severity.CRITICAL), 1),
    ],
)
def test_exit_code_matches_legacy_contract(severities, expected) -> None:
    report = _report(headline="h", summary={"matrix": []}, severities=severities)
    assert report.exit_code == expected
