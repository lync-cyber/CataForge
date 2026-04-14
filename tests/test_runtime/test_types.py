"""测试平台无关数据类型。"""
import pytest
from runtime.types import AgentStatus, DispatchRequest, AgentResult, CAPABILITY_IDS


class TestAgentStatus:
    def test_all_enum_values(self):
        expected = {
            "completed", "needs_input", "blocked", "approved",
            "approved_with_notes", "needs_revision", "rolled-back",
        }
        actual = {s.value for s in AgentStatus}
        assert actual == expected

    def test_from_string(self):
        assert AgentStatus("completed") == AgentStatus.COMPLETED
        assert AgentStatus("needs_input") == AgentStatus.NEEDS_INPUT


class TestDispatchRequest:
    def test_minimal_creation(self):
        req = DispatchRequest(
            agent_id="architect",
            task="设计架构",
            task_type="new_creation",
            input_docs=["docs/prd/prd-v1.md"],
            expected_output="docs/arch/",
            phase="architecture",
            project_name="test",
        )
        assert req.agent_id == "architect"
        assert req.background is False
        assert req.max_turns is None


class TestAgentResult:
    def test_creation(self):
        result = AgentResult(
            status=AgentStatus.COMPLETED,
            outputs=["docs/arch/arch-v1.md"],
            summary="完成",
        )
        assert result.status == AgentStatus.COMPLETED
        assert len(result.outputs) == 1


class TestCapabilityIDs:
    def test_all_ids_present(self):
        assert "file_read" in CAPABILITY_IDS
        assert "agent_dispatch" in CAPABILITY_IDS
        assert len(CAPABILITY_IDS) == 10
