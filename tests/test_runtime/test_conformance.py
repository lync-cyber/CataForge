"""测试平台合规检查。"""
import pytest
from runtime.conformance import check_conformance


class TestCheckConformance:
    def test_claude_code_passes(self):
        issues = check_conformance("claude-code")
        fails = [i for i in issues if i.startswith("FAIL")]
        assert len(fails) == 0

    def test_cursor_passes(self):
        issues = check_conformance("cursor")
        fails = [i for i in issues if i.startswith("FAIL")]
        assert len(fails) == 0

    def test_codex_warns_on_null_capabilities(self):
        issues = check_conformance("codex")
        warns = [i for i in issues if "user_question" in i]
        assert len(warns) == 0  # user_question not required

    def test_opencode_passes(self):
        issues = check_conformance("opencode")
        fails = [i for i in issues if i.startswith("FAIL")]
        assert len(fails) == 0
