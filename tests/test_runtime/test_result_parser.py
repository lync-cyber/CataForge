"""测试 Agent 返回值容错解析。"""
import pytest
from runtime.result_parser import parse_agent_result
from runtime.types import AgentStatus


class TestParseAgentResult:
    def test_full_xml(self):
        text = """
        <agent-result>
        <status>completed</status>
        <outputs>docs/arch/arch-v1.md</outputs>
        <summary>架构设计完成</summary>
        </agent-result>
        """
        result = parse_agent_result(text)
        assert result is not None
        assert result.status == AgentStatus.COMPLETED
        assert result.outputs == ["docs/arch/arch-v1.md"]
        assert result.summary == "架构设计完成"

    def test_needs_input_with_questions(self):
        text = """
        <agent-result>
        <status>needs_input</status>
        <outputs>docs/arch/arch-v1.md</outputs>
        <summary>需要确认</summary>
        </agent-result>
        <questions>[{"id":"Q1","text":"选择数据库"}]</questions>
        <completed-steps>Step 1, Step 2</completed-steps>
        <resume-guidance>从Step 3恢复</resume-guidance>
        """
        result = parse_agent_result(text)
        assert result is not None
        assert result.status == AgentStatus.NEEDS_INPUT
        assert result.questions is not None
        assert len(result.questions) == 1
        assert result.completed_steps == "Step 1, Step 2"
        assert result.resume_guidance == "从Step 3恢复"

    def test_missing_agent_result_tag(self):
        text = "任务完成了，所有文件已创建。"
        result = parse_agent_result(text)
        assert result is None

    def test_partial_tags(self):
        text = "<status>completed</status><outputs>file.md</outputs>"
        result = parse_agent_result(text)
        assert result is not None
        assert result.status == AgentStatus.COMPLETED

    def test_missing_status_defaults_to_completed(self):
        text = """
        <agent-result>
        <outputs>file.md</outputs>
        <summary>done</summary>
        </agent-result>
        """
        result = parse_agent_result(text)
        assert result is not None
        assert result.status == AgentStatus.COMPLETED
