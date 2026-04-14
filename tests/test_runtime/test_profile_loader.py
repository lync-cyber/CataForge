"""测试 profile 加载和工具名解析。"""
import pytest
from runtime.profile_loader import (
    load_profile, get_tool_map, resolve_tool_name, resolve_tools_list,
)


class TestLoadProfile:
    def test_claude_code_profile(self):
        profile = load_profile("claude-code")
        assert profile["platform_id"] == "claude-code"
        assert profile["tool_map"]["shell_exec"] == "Bash"

    def test_cursor_profile(self):
        profile = load_profile("cursor")
        assert profile["tool_map"]["file_edit"] == "StrReplace"
        assert profile["tool_map"]["shell_exec"] == "Shell"
        assert profile["tool_map"]["agent_dispatch"] == "Task"

    def test_all_profiles_have_required_fields(self):
        for pid in ["claude-code", "cursor", "codex", "opencode"]:
            profile = load_profile(pid)
            assert "platform_id" in profile
            assert "tool_map" in profile
            assert "dispatch" in profile
            assert "hooks" in profile


class TestResolveToolName:
    def test_claude_code_dispatch(self):
        assert resolve_tool_name("agent_dispatch", "claude-code") == "Agent"

    def test_cursor_dispatch(self):
        assert resolve_tool_name("agent_dispatch", "cursor") == "Task"

    def test_unsupported_capability_returns_none(self):
        assert resolve_tool_name("user_question", "cursor") is None

    def test_resolve_tools_list_skips_unsupported(self):
        caps = ["file_read", "user_question", "agent_dispatch"]
        result = resolve_tools_list(caps, "cursor")
        assert "Read" in result
        assert "Task" in result
        assert len(result) == 2
