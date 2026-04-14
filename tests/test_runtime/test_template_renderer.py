"""测试模板 Override 渲染。"""
import pytest
from runtime.template_renderer import render_template, list_override_points


class TestOverridePoints:
    def test_dispatch_prompt_has_expected_points(self):
        points = list_override_points(
            "skills/agent-dispatch/templates/dispatch-prompt.md"
        )
        expected = {
            "dispatch_syntax", "startup_notes", "return_format",
            "tool_usage", "context_limits",
        }
        assert expected == set(points)


class TestRenderTemplate:
    def test_claude_code_uses_defaults(self):
        result = render_template(
            "skills/agent-dispatch/templates/dispatch-prompt.md",
            "claude-code",
        )
        assert "Agent tool:" in result or "subagent_type" in result
        assert "<!-- OVERRIDE:" not in result

    def test_cursor_override_applied(self):
        result = render_template(
            "skills/agent-dispatch/templates/dispatch-prompt.md",
            "cursor",
        )
        assert "Task:" in result
        assert "StrReplace" in result
        assert "<!-- OVERRIDE:" not in result

    def test_codex_override_applied(self):
        result = render_template(
            "skills/agent-dispatch/templates/dispatch-prompt.md",
            "codex",
        )
        assert "spawn_agent" in result
        assert "上下文限制" in result
