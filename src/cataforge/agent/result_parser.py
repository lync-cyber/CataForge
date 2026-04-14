"""Agent result 4-level fault-tolerant parser.

Parse priority:
1. Normal: extract <agent-result> XML tag
2. Tag missing: infer completed (if output files present)
3. Incomplete fields: fill defaults
4. Truncation recovery: detect unclosed tags
"""

from __future__ import annotations

import contextlib
import json
import re

from cataforge.core.types import AgentResult, AgentStatus


def parse_agent_result(text: str) -> AgentResult | None:
    """Parse a structured result from agent return text.

    Returns AgentResult or None if completely unparseable.
    """
    result = _try_xml_parse(text)
    if result:
        return result

    result = _try_partial_parse(text)
    if result:
        return result

    return None


def _try_xml_parse(text: str) -> AgentResult | None:
    m = re.search(r"<agent-result>\s*(.*?)\s*</agent-result>", text, re.DOTALL)
    if not m:
        return None

    block = m.group(1)
    status = _extract_tag(block, "status")
    outputs = _extract_tag(block, "outputs")
    summary = _extract_tag(block, "summary")

    if not status:
        status = "completed" if outputs else "blocked"

    try:
        agent_status = AgentStatus(status)
    except ValueError:
        agent_status = AgentStatus.COMPLETED

    output_list = [o.strip() for o in (outputs or "").split(",") if o.strip()]

    result = AgentResult(status=agent_status, outputs=output_list, summary=summary or "")

    questions_str = _extract_tag(text, "questions")
    if questions_str:
        with contextlib.suppress(json.JSONDecodeError, ValueError):
            result.questions = json.loads(questions_str)

    completed = _extract_tag(text, "completed-steps")
    if completed:
        result.completed_steps = completed

    guidance = _extract_tag(text, "resume-guidance")
    if guidance:
        result.resume_guidance = guidance

    return result


def _try_partial_parse(text: str) -> AgentResult | None:
    status = _extract_tag(text, "status")
    outputs = _extract_tag(text, "outputs")
    summary = _extract_tag(text, "summary")

    if not any([status, outputs, summary]):
        return None

    if not status:
        status = "completed" if outputs else "blocked"

    try:
        agent_status = AgentStatus(status)
    except ValueError:
        agent_status = AgentStatus.COMPLETED

    output_list = [o.strip() for o in (outputs or "").split(",") if o.strip()]
    return AgentResult(status=agent_status, outputs=output_list, summary=summary or "")


def _extract_tag(text: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return m.group(1).strip() if m else None
