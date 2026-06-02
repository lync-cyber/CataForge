"""Tests: _try_partial_parse requires <agent-result> container; questions JSON errors logged."""

from __future__ import annotations

import logging

from cataforge.core.types import AgentStatus
from cataforge.runtime.agent.result_parser import parse_agent_result


def test_bare_status_tag_in_markdown_no_container_returns_incomplete():
    text = "Here is my reply:\n```python\n<status>OK</status>\n```\nNo container here."
    result = parse_agent_result(text)
    assert result is None


def test_status_inside_container_parses_correctly():
    text = (
        "<agent-result>"
        "<status>completed</status>"
        "<outputs>file.py</outputs>"
        "<summary>done</summary>"
        "</agent-result>"
    )
    result = parse_agent_result(text)
    assert result is not None
    assert result.status == AgentStatus.COMPLETED
    assert result.outputs == ["file.py"]
    assert result.summary == "done"


def test_truncated_response_with_container_partial_parse():
    # outputs tag is mid-truncation (no close tag), but status is intact
    text = "<agent-result><status>completed</status><outputs>file.py"
    result = parse_agent_result(text)
    assert result is not None
    assert result.status == AgentStatus.COMPLETED
    # truncated outputs tag has no close — outputs list is empty, not a false positive
    assert result.outputs == []


def test_plain_text_no_tags_returns_none():
    text = "Everything went fine, no XML here at all."
    result = parse_agent_result(text)
    assert result is None


def test_questions_invalid_json_logs_debug_and_questions_none(caplog):
    text = (
        "<agent-result>"
        "<status>needs_input</status>"
        "<outputs></outputs>"
        "<summary>need info</summary>"
        '<questions>{ "broken": </questions>'
        "</agent-result>"
    )
    with caplog.at_level(logging.DEBUG, logger="cataforge.runtime.agent.result_parser"):
        result = parse_agent_result(text)

    assert result is not None
    assert result.status == AgentStatus.NEEDS_INPUT
    assert result.questions is None
    assert any("unparseable" in record.message for record in caplog.records)
