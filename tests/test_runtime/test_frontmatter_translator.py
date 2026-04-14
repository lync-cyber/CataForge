"""测试 AGENT.md frontmatter 翻译。"""
import pytest
from runtime.frontmatter_translator import translate_agent_md


class TestTranslateAgentMd:
    SAMPLE_MD = """---
name: orchestrator
tools: file_read, file_write, file_edit, file_glob, file_grep, shell_exec, agent_dispatch, user_question
disallowedTools: []
---
# Role: orchestrator
"""

    def test_claude_code_translation(self):
        result = translate_agent_md(self.SAMPLE_MD, "claude-code")
        assert "tools: Read, Write, Edit, Glob, Grep, Bash, Agent, AskUserQuestion" in result

    def test_cursor_translation(self):
        result = translate_agent_md(self.SAMPLE_MD, "cursor")
        assert "StrReplace" in result
        assert "Shell" in result
        assert "Task" in result
        assert "AskUserQuestion" not in result

    def test_body_unchanged(self):
        result = translate_agent_md(self.SAMPLE_MD, "cursor")
        assert "# Role: orchestrator" in result

    def test_codex_translation(self):
        result = translate_agent_md(self.SAMPLE_MD, "codex")
        assert "apply_patch" in result
        assert "spawn_agent" in result
