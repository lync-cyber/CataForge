from __future__ import annotations

from cataforge.runtime.deploy.capability_report import (
    evaluate_capability_report,
    summarize_capability_report,
)


def test_report_evaluation_surfaces_conditional_and_unenforced_state() -> None:
    report = {
        "report_version": 1,
        "platform": "codex",
        "agent_tool_policy": "inherit_only",
        "capabilities": {
            "user_question": {
                "status": "conditional",
                "reason": "available only in the root thread",
            },
            "web_fetch": {
                "status": "replacement",
                "tool": "web.search_query",
            },
        },
        "agents": {
            "reviewer": {
                "unenforced": ["shell"],
            }
        },
    }

    assert summarize_capability_report(report) == {
        "tool_policy": "inherit_only",
        "conditional": 1,
        "unenforced_agents": 1,
    }
    assert evaluate_capability_report(
        report,
        "codex",
        {"user_question", "web_fetch"},
    ) == [
        "INFO: codex capability user_question is conditional: available only in the root thread",
        "INFO: codex capability web_fetch uses replacement tool 'web.search_query'",
        "WARN: codex has 1 agent(s) with unenforced capability policy",
    ]


def test_report_evaluation_rejects_wrong_platform_and_missing_capability() -> None:
    report = {
        "report_version": 1,
        "platform": "claude-code",
        "capabilities": {},
        "agents": {},
    }

    assert evaluate_capability_report(report, "codex", {"user_question"}) == [
        "FAIL: capability report platform mismatch ('claude-code' != 'codex')",
        "FAIL: codex capability report is missing user_question",
    ]
