"""测试 Hook 桥接层。"""
import pytest
from runtime.hook_bridge import (
    generate_platform_hooks, get_degraded_hooks, load_hooks_spec,
)


class TestLoadHooksSpec:
    def test_loads_successfully(self):
        spec = load_hooks_spec()
        assert "hooks" in spec
        assert "PreToolUse" in spec["hooks"]
        assert "degradation_templates" in spec


class TestGeneratePlatformHooks:
    def test_claude_code_all_native(self):
        hooks = generate_platform_hooks("claude-code")
        assert "PreToolUse" in hooks
        assert "PostToolUse" in hooks
        assert "Stop" in hooks

    def test_cursor_translates_event_names(self):
        hooks = generate_platform_hooks("cursor")
        assert "preToolUse" in hooks
        assert "PreToolUse" not in hooks

    def test_opencode_empty(self):
        hooks = generate_platform_hooks("opencode")
        assert hooks == {}


class TestDegradedHooks:
    def test_claude_code_no_degradation(self):
        degraded = get_degraded_hooks("claude-code")
        assert len(degraded) == 0

    def test_opencode_all_degraded(self):
        degraded = get_degraded_hooks("opencode")
        names = [d["name"] for d in degraded]
        assert "guard_dangerous" in names
        assert len(degraded) >= 6

    def test_codex_partial_degradation(self):
        degraded = get_degraded_hooks("codex")
        names = [d["name"] for d in degraded]
        assert "log_agent_dispatch" in names
        assert "guard_dangerous" not in names
