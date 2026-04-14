"""Tests for platform adapters."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cataforge.platform.registry import get_adapter


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """Create a project with platform profiles."""
    cataforge_dir = tmp_path / ".cataforge"
    cataforge_dir.mkdir()

    fw = {"version": "0.1.0", "runtime": {"platform": "claude-code"}}
    (cataforge_dir / "framework.json").write_text(json.dumps(fw), encoding="utf-8")

    platforms_dir = cataforge_dir / "platforms"
    for pid, data in _PROFILES.items():
        (platforms_dir / pid).mkdir(parents=True)
        with open(platforms_dir / pid / "profile.yaml", "w", encoding="utf-8") as f:
            yaml.dump(data, f)

    return tmp_path


_PROFILES = {
    "claude-code": {
        "platform_id": "claude-code",
        "display_name": "Claude Code",
        "tool_map": {
            "file_read": "Read",
            "file_write": "Write",
            "file_edit": "Edit",
            "shell_exec": "Bash",
            "agent_dispatch": "Agent",
        },
        "extended_capabilities": {
            "notebook_edit": "NotebookEdit",
            "browser_preview": "preview_start",
            "image_input": "Read",
            "code_review": None,
        },
        "agent_definition": {
            "format": "yaml-frontmatter",
            "scan_dirs": [".claude/agents"],
            "needs_deploy": True,
        },
        "agent_config": {
            "supported_fields": [
                "name", "description", "tools", "disallowedTools", "model",
                "permissionMode", "maxTurns", "skills", "mcpServers", "hooks",
                "memory", "background", "effort", "isolation", "color",
                "initialPrompt", "prompt",
            ],
            "memory_scopes": ["user", "project", "local"],
            "isolation_modes": ["worktree"],
        },
        "instruction_file": {"reads_claude_md": True, "additional_outputs": []},
        "dispatch": {"tool_name": "Agent", "is_async": False},
        "hooks": {
            "config_format": "json",
            "config_path": ".claude/settings.json",
            "event_map": {"PreToolUse": "PreToolUse", "PostToolUse": "PostToolUse"},
            "degradation": {"guard_dangerous": "native"},
        },
        "features": {
            "cloud_agents": False,
            "agent_teams": True,
            "parallel_agents": True,
            "background_agents": True,
            "plan_mode": True,
            "multi_model": True,
            "agent_memory": True,
            "context_management": True,
        },
        "permissions": {"modes": ["default", "acceptEdits", "auto", "bypassPermissions", "plan"]},
        "model_routing": {"available_models": ["opus", "sonnet", "haiku"], "per_agent_model": True},
    },
    "cursor": {
        "platform_id": "cursor",
        "display_name": "Cursor",
        "tool_map": {
            "file_read": "Read",
            "file_write": "Write",
            "file_edit": "Write",
            "shell_exec": "Shell",
            "agent_dispatch": "Task",
        },
        "extended_capabilities": {
            "notebook_edit": None,
            "browser_preview": "computer",
            "image_input": None,
            "code_review": None,
        },
        "agent_definition": {
            "format": "yaml-frontmatter",
            "scan_dirs": [".cursor/agents", ".claude/agents"],
            "needs_deploy": True,
        },
        "agent_config": {
            "supported_fields": [
                "name", "description", "tools", "disallowedTools",
                "model", "maxTurns", "mcpServers", "hooks", "background",
            ],
            "memory_scopes": [],
            "isolation_modes": ["worktree"],
        },
        "instruction_file": {
            "reads_claude_md": True,
            "additional_outputs": [{"target": ".cursor/rules/", "format": "mdc"}],
        },
        "dispatch": {"tool_name": "Task", "is_async": False},
        "hooks": {
            "config_format": "json",
            "config_path": ".cursor/hooks.json",
            "event_map": {"PreToolUse": "preToolUse", "PostToolUse": "postToolUse"},
            "tool_overrides": {},
            "degradation": {"guard_dangerous": "native", "lint_format": "native"},
        },
        "features": {
            "cloud_agents": True,
            "parallel_agents": True,
            "autonomy_slider": True,
            "plugin_marketplace": True,
        },
        "permissions": {"modes": ["default", "auto"]},
        "model_routing": {
            "available_models": ["opus", "sonnet", "gpt-5.4"],
            "per_agent_model": True,
        },
    },
    "codex": {
        "platform_id": "codex",
        "display_name": "Codex CLI",
        "tool_map": {
            "file_read": "shell",
            "shell_exec": "shell",
            "agent_dispatch": "spawn_agent",
        },
        "extended_capabilities": {
            "notebook_edit": None,
            "image_input": "image",
            "code_review": "review",
        },
        "agent_definition": {
            "format": "toml",
            "scan_dirs": [".codex/agents"],
            "needs_deploy": True,
        },
        "agent_config": {
            "supported_fields": [
                "name", "description", "model",
                "model_reasoning_effort", "sandbox_mode",
            ],
            "memory_scopes": [],
            "isolation_modes": [],
        },
        "instruction_file": {"reads_claude_md": True},
        "dispatch": {"tool_name": "spawn_agent", "is_async": True},
        "hooks": {
            "config_format": "json",
            "config_path": ".codex/hooks.json",
            "event_map": {"PreToolUse": "PreToolUse", "PostToolUse": "PostToolUse"},
            "tool_overrides": {"shell_exec": "Bash"},
            "degradation": {"guard_dangerous": "native"},
        },
        "features": {
            "cloud_agents": True,
            "computer_use": True,
            "realtime_voice": True,
            "session_resume": True,
            "multi_root": True,
        },
        "permissions": {"modes": ["auto", "read_only", "full_access"]},
        "model_routing": {"available_models": ["gpt-5.4"], "per_agent_model": False},
    },
    "opencode": {
        "platform_id": "opencode",
        "display_name": "OpenCode",
        "tool_map": {
            "file_read": "read",
            "shell_exec": "bash",
            "agent_dispatch": "task",
        },
        "extended_capabilities": {
            "image_input": "image",
        },
        "agent_definition": {
            "format": "yaml-frontmatter",
            "scan_dirs": [".claude/agents"],
            "needs_deploy": False,
        },
        "agent_config": {
            "supported_fields": ["name", "description", "tools", "model"],
        },
        "instruction_file": {"reads_claude_md": True},
        "dispatch": {"tool_name": "task"},
        "hooks": {"config_format": None, "degradation": {}},
        "features": {
            "plan_mode": True,
            "multi_model": True,
            "ci_cd_integration": True,
            "session_resume": True,
        },
        "permissions": {"modes": ["default"]},
        "model_routing": {"available_models": [], "per_agent_model": True},
    },
}


class TestAdapterCreation:
    def test_claude_code(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        assert adapter.platform_id == "claude-code"
        assert adapter.display_name == "Claude Code"

    def test_cursor(self, project_dir: Path) -> None:
        adapter = get_adapter("cursor", project_dir / ".cataforge" / "platforms")
        assert adapter.platform_id == "cursor"
        assert adapter.display_name == "Cursor"

    def test_codex(self, project_dir: Path) -> None:
        adapter = get_adapter("codex", project_dir / ".cataforge" / "platforms")
        assert adapter.platform_id == "codex"

    def test_opencode(self, project_dir: Path) -> None:
        adapter = get_adapter("opencode", project_dir / ".cataforge" / "platforms")
        assert adapter.platform_id == "opencode"


class TestToolMapping:
    def test_claude_code_tools(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        assert adapter.resolve_tool_name("shell_exec") == "Bash"
        assert adapter.resolve_tool_name("agent_dispatch") == "Agent"

    def test_cursor_tools(self, project_dir: Path) -> None:
        adapter = get_adapter("cursor", project_dir / ".cataforge" / "platforms")
        assert adapter.resolve_tool_name("file_edit") == "Write"
        assert adapter.resolve_tool_name("shell_exec") == "Shell"
        assert adapter.resolve_tool_name("agent_dispatch") == "Task"


class TestExtendedCapabilities:
    def test_claude_code_extended(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        ext = adapter.get_extended_tool_map()
        assert ext["notebook_edit"] == "NotebookEdit"
        assert ext["browser_preview"] == "preview_start"
        assert ext["code_review"] is None

    def test_full_tool_map_includes_extended(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        full = adapter.get_full_tool_map()
        assert "file_read" in full  # core
        assert "notebook_edit" in full  # extended
        assert full["file_read"] == "Read"
        assert full["notebook_edit"] == "NotebookEdit"

    def test_resolve_tool_name_includes_extended(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        assert adapter.resolve_tool_name("notebook_edit") == "NotebookEdit"
        assert adapter.resolve_tool_name("code_review") is None

    def test_codex_extended(self, project_dir: Path) -> None:
        adapter = get_adapter("codex", project_dir / ".cataforge" / "platforms")
        ext = adapter.get_extended_tool_map()
        assert ext.get("image_input") == "image"
        assert ext.get("code_review") == "review"

    def test_empty_extended_capabilities(self, project_dir: Path) -> None:
        adapter = get_adapter("opencode", project_dir / ".cataforge" / "platforms")
        ext = adapter.get_extended_tool_map()
        assert ext.get("image_input") == "image"
        assert ext.get("notebook_edit") is None


class TestAgentConfig:
    def test_claude_code_supported_fields(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        fields = adapter.agent_supported_fields
        assert "name" in fields
        assert "memory" in fields
        assert "isolation" in fields
        assert "effort" in fields
        assert len(fields) == 17

    def test_claude_code_memory_scopes(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        assert adapter.agent_memory_scopes == ["user", "project", "local"]

    def test_codex_limited_fields(self, project_dir: Path) -> None:
        adapter = get_adapter("codex", project_dir / ".cataforge" / "platforms")
        fields = adapter.agent_supported_fields
        assert "name" in fields
        assert "model" in fields
        assert "memory" not in fields

    def test_opencode_minimal_fields(self, project_dir: Path) -> None:
        adapter = get_adapter("opencode", project_dir / ".cataforge" / "platforms")
        fields = adapter.agent_supported_fields
        assert fields == ["name", "description", "tools", "model"]

    def test_cursor_isolation_modes(self, project_dir: Path) -> None:
        adapter = get_adapter("cursor", project_dir / ".cataforge" / "platforms")
        assert adapter.agent_isolation_modes == ["worktree"]


class TestPlatformFeatures:
    def test_claude_code_features(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        features = adapter.get_supported_features()
        assert features["agent_teams"] is True
        assert features["plan_mode"] is True
        assert features["cloud_agents"] is False

    def test_supports_feature(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        assert adapter.supports_feature("multi_model") is True
        assert adapter.supports_feature("cloud_agents") is False
        assert adapter.supports_feature("nonexistent") is False

    def test_cursor_features(self, project_dir: Path) -> None:
        adapter = get_adapter("cursor", project_dir / ".cataforge" / "platforms")
        assert adapter.supports_feature("cloud_agents") is True
        assert adapter.supports_feature("autonomy_slider") is True

    def test_codex_features(self, project_dir: Path) -> None:
        adapter = get_adapter("codex", project_dir / ".cataforge" / "platforms")
        assert adapter.supports_feature("computer_use") is True
        assert adapter.supports_feature("session_resume") is True


class TestPermissions:
    def test_claude_code_modes(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        modes = adapter.permission_modes
        assert "default" in modes
        assert "auto" in modes
        assert "bypassPermissions" in modes

    def test_codex_modes(self, project_dir: Path) -> None:
        adapter = get_adapter("codex", project_dir / ".cataforge" / "platforms")
        modes = adapter.permission_modes
        assert "auto" in modes
        assert "read_only" in modes
        assert "full_access" in modes


class TestModelRouting:
    def test_claude_code_models(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        assert adapter.available_models == ["opus", "sonnet", "haiku"]
        assert adapter.supports_per_agent_model is True

    def test_codex_no_per_agent(self, project_dir: Path) -> None:
        adapter = get_adapter("codex", project_dir / ".cataforge" / "platforms")
        assert adapter.supports_per_agent_model is False

    def test_opencode_no_models(self, project_dir: Path) -> None:
        adapter = get_adapter("opencode", project_dir / ".cataforge" / "platforms")
        assert adapter.available_models == []
        assert adapter.supports_per_agent_model is True


class TestHookCommandTemplate:
    def test_hook_template_uses_python_m(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        template = adapter.get_hook_command_template()
        assert template == "python -m cataforge.hook.scripts.{module}"
        cmd = template.format(module="guard_dangerous")
        assert "cataforge.hook.scripts.guard_dangerous" in cmd

    def test_all_platforms_share_same_template(self, project_dir: Path) -> None:
        platforms_dir = project_dir / ".cataforge" / "platforms"
        for pid in ("claude-code", "cursor", "opencode"):
            adapter = get_adapter(pid, platforms_dir)
            expected = "python -m cataforge.hook.scripts.{module}"
            assert adapter.get_hook_command_template() == expected
