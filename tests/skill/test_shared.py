"""Tests for the shared Layer 1 issue/report model (skill.builtins._shared)."""

from __future__ import annotations

from cataforge.core.types import Severity
from cataforge.runtime.skill.builtins._shared import (
    CheckReport,
    IssueCollector,
)


def _collector(*severities: Severity) -> IssueCollector:
    c = IssueCollector()
    for i, sev in enumerate(severities):
        c.add(sev, "cat", f"msg-{i}")
    return c


def test_exit_code_clean_when_no_issues() -> None:
    assert CheckReport(IssueCollector()).exit_code == 0


def test_exit_code_blocking_takes_precedence() -> None:
    report = CheckReport(_collector(Severity.LOW, Severity.CRITICAL))
    assert report.exit_code == 1


def test_exit_code_advisory_only() -> None:
    report = CheckReport(_collector(Severity.MEDIUM, Severity.LOW))
    assert report.exit_code == 2


def test_to_dict_serializes_issues_and_exit_code() -> None:
    report = CheckReport(_collector(Severity.HIGH))
    payload = report.to_dict()
    assert payload["exit_code"] == 1
    assert payload["summary"] == {}
    assert [i["severity"] for i in payload["issues"]] == ["HIGH"]
    assert "headline" not in payload


def test_to_dict_includes_headline_and_summary_when_present() -> None:
    report = CheckReport(
        IssueCollector(),
        summary={"matrix": [{"feature": "F-001"}]},
        headline="检查: foo.md",
    )
    payload = report.to_dict()
    assert payload["headline"] == "检查: foo.md"
    assert payload["summary"] == {"matrix": [{"feature": "F-001"}]}
    assert payload["exit_code"] == 0


def test_summary_defaults_are_independent() -> None:
    a = CheckReport(IssueCollector())
    b = CheckReport(IssueCollector())
    a.summary["k"] = 1
    assert b.summary == {}
