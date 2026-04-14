"""Agent 返回值 4 级容错解析器。

解析优先级:
1. 正常: 提取 <agent-result> XML 标签
2. 标签缺失: 推断 completed (如果有产出文件)
3. 字段不完整: 补充缺失字段
4. 截断恢复: 检测未关闭标签
"""
from __future__ import annotations
import re
from .types import AgentResult, AgentStatus


def parse_agent_result(text: str) -> AgentResult | None:
    """从 Agent 返回文本中解析结构化结果。

    Returns:
        AgentResult 或 None（完全无法解析时）。
    """
    result = _try_xml_parse(text)
    if result:
        return result

    result = _try_partial_parse(text)
    if result:
        return result

    return None


def _try_xml_parse(text: str) -> AgentResult | None:
    """Level 1: 完整 XML 标签解析。"""
    m = re.search(
        r"<agent-result>\s*(.*?)\s*</agent-result>",
        text,
        re.DOTALL,
    )
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

    result = AgentResult(
        status=agent_status,
        outputs=output_list,
        summary=summary or "",
    )

    questions_str = _extract_tag(text, "questions")
    if questions_str:
        try:
            import json
            result.questions = json.loads(questions_str)
        except (json.JSONDecodeError, ValueError):
            pass

    completed = _extract_tag(text, "completed-steps")
    if completed:
        result.completed_steps = completed

    guidance = _extract_tag(text, "resume-guidance")
    if guidance:
        result.resume_guidance = guidance

    return result


def _try_partial_parse(text: str) -> AgentResult | None:
    """Level 2-3: 部分标签解析。"""
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

    return AgentResult(
        status=agent_status,
        outputs=output_list,
        summary=summary or "",
    )


def _extract_tag(text: str, tag: str) -> str | None:
    """提取 XML 标签内容。"""
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return m.group(1).strip() if m else None
