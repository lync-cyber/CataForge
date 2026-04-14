"""Tests for hook bridge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cataforge.hook.bridge import generate_platform_hooks
from cataforge.platform.registry import get_adapter


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """Create project with hooks.yaml and platform profiles."""
    cataforge_dir = tmp_path / ".cataforge"
    cataforge_dir.mkdir()

    (cataforge_dir / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )

    hooks_dir = cataforge_dir / "hooks"
    hooks_dir.mkdir()
    hooks_spec = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher_capability": "shell_exec",
                    "script": "guard_dangerous",
                    "type": "block",
                }
            ],
            "PostToolUse": [
                {
                    "matcher_capability": "file_edit",
                    "script": "lint_format",
                    "type": "observe",
                }
            ],
        },
        "degradation_templates": {},
    }
    with open(hooks_dir / "hooks.yaml", "w", encoding="utf-8") as f:
        yaml.dump(hooks_spec, f)

    for pid, profile in {
        "claude-code": {
            "platform_id": "claude-code",
            "tool_map": {"shell_exec": "Bash", "file_edit": "Edit", "file_write": "Write"},
            "hooks": {
                "config_format": "json",
                "config_path": ".claude/settings.json",
                "event_map": {"PreToolUse": "PreToolUse", "PostToolUse": "PostToolUse"},
                "degradation": {"guard_dangerous": "native", "lint_format": "native"},
            },
        },
        "cursor": {
            "platform_id": "cursor",
            "tool_map": {"shell_exec": "Shell", "file_edit": "Write", "file_write": "Write"},
            "hooks": {
                "config_format": "json",
                "config_path": ".cursor/hooks.json",
                "event_map": {"PreToolUse": "preToolUse", "PostToolUse": "postToolUse"},
                "tool_overrides": {},
                "degradation": {"guard_dangerous": "native", "lint_format": "native"},
            },
        },
        "codex": {
            "platform_id": "codex",
            "tool_map": {"shell_exec": "shell", "file_edit": "apply_patch"},
            "hooks": {
                "config_format": "json",
                "config_path": ".codex/hooks.json",
                "event_map": {"PreToolUse": "PreToolUse", "PostToolUse": "PostToolUse"},
                "tool_overrides": {"shell_exec": "Bash"},
                "degradation": {"guard_dangerous": "native", "lint_format": "degraded"},
            },
        },
    }.items():
        p = cataforge_dir / "platforms" / pid
        p.mkdir(parents=True)
        with open(p / "profile.yaml", "w", encoding="utf-8") as f:
            yaml.dump(profile, f)

    return tmp_path


class TestHookBridge:
    def test_claude_code_hooks(self, project_dir: Path) -> None:
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("claude-code", platforms_dir)

        hooks = generate_platform_hooks(adapter)

        assert "PreToolUse" in hooks
        pre = hooks["PreToolUse"]
        assert len(pre) == 1
        assert pre[0]["matcher"] == "Bash"
        cmd = pre[0]["hooks"][0]["command"]
        assert "python -m cataforge.hook.scripts.guard_dangerous" in cmd

    def test_cursor_hooks_use_module_invocation(self, project_dir: Path) -> None:
        """Hooks are invoked via python -m cataforge.hook.scripts.<module>."""
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("cursor", platforms_dir)

        hooks = generate_platform_hooks(adapter)

        assert "preToolUse" in hooks
        pre = hooks["preToolUse"]
        cmd = pre[0]["hooks"][0]["command"]
        assert "python -m cataforge.hook.scripts.guard_dangerous" in cmd

    def test_cursor_uses_platform_tool_names(self, project_dir: Path) -> None:
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("cursor", platforms_dir)

        hooks = generate_platform_hooks(adapter)

        pre = hooks["preToolUse"]
        assert pre[0]["matcher"] == "Shell"  # not "Bash"

        post = hooks["postToolUse"]
        assert post[0]["matcher"] == "Write"  # not "Edit"

    def test_codex_tool_overrides_used_for_matcher(self, project_dir: Path) -> None:
        """hook_tool_overrides take precedence over tool_map for matchers."""
        platforms_dir = project_dir / ".cataforge" / "platforms"
        adapter = get_adapter("codex", platforms_dir)

        hooks = generate_platform_hooks(adapter)

        # shell_exec tool_map="shell" but tool_overrides="Bash"
        pre = hooks["PreToolUse"]
        assert pre[0]["matcher"] == "Bash"  # from tool_overrides, not "shell"
