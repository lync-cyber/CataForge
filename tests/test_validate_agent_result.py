"""validate_agent_result.py agent-result 校验测试"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))
from validate_agent_result import VALID_STATUSES


def check_result(result_text: str) -> list[str]:
    """模拟 validate_agent_result.py 的检测逻辑，返回警告列表"""
    warnings = []

    if "<agent-result>" not in result_text:
        warnings.append("missing <agent-result> tag")
        return warnings

    for field in ("status", "outputs", "summary"):
        if not re.search(rf"<{field}>[\s\S]*?</{field}>", result_text):
            warnings.append(f"missing <{field}> field")

    m = re.search(r"<status>\s*(.*?)\s*</status>", result_text)
    if m:
        status = m.group(1).strip()
        if status not in VALID_STATUSES:
            warnings.append(f"invalid status='{status}'")
        if status == "needs_input" and "<questions>" not in result_text:
            warnings.append("status=needs_input but missing <questions>")

    return warnings


# ── 合法结果 ─────────────────────────────────────────────────────────────


class TestValidResults:
    @pytest.mark.parametrize("status", sorted(VALID_STATUSES))
    def test_valid_status(self, status):
        extra = "<questions>Q1</questions>" if status == "needs_input" else ""
        result = (
            f"<agent-result><status>{status}</status>"
            f"<outputs>f.md</outputs><summary>done</summary>"
            f"{extra}</agent-result>"
        )
        warnings = check_result(result)
        assert len(warnings) == 0, f"status={status} 应无警告: {warnings}"

    def test_all_statuses_present(self):
        """确保 VALID_STATUSES 包含 COMMON-RULES 中定义的全部 7 个状态码"""
        expected = {
            "completed",
            "needs_input",
            "blocked",
            "rolled-back",
            "approved",
            "approved_with_notes",
            "needs_revision",
        }
        assert VALID_STATUSES == expected


# ── 缺失标签 ─────────────────────────────────────────────────────────────


class TestMissingTags:
    def test_no_agent_result_tag(self):
        warnings = check_result("just some text without tags")
        assert any("missing <agent-result>" in w for w in warnings)

    def test_missing_status(self):
        result = "<agent-result><outputs>f</outputs><summary>s</summary></agent-result>"
        warnings = check_result(result)
        assert any("missing <status>" in w for w in warnings)

    def test_missing_outputs(self):
        result = "<agent-result><status>completed</status><summary>s</summary></agent-result>"
        warnings = check_result(result)
        assert any("missing <outputs>" in w for w in warnings)

    def test_missing_summary(self):
        result = "<agent-result><status>completed</status><outputs>f</outputs></agent-result>"
        warnings = check_result(result)
        assert any("missing <summary>" in w for w in warnings)


# ── 无效状态 ─────────────────────────────────────────────────────────────


class TestInvalidStatus:
    def test_unknown_status(self):
        result = "<agent-result><status>unknown</status><outputs>f</outputs><summary>s</summary></agent-result>"
        warnings = check_result(result)
        assert any("invalid status" in w for w in warnings)

    def test_needs_input_without_questions(self):
        result = (
            "<agent-result><status>needs_input</status>"
            "<outputs>f</outputs><summary>s</summary></agent-result>"
        )
        warnings = check_result(result)
        assert any("missing <questions>" in w for w in warnings)
