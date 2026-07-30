"""Tests for platform adapters."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from cataforge.adapter.platform.registry import get_adapter
from cataforge.runtime.deploy import steps
from tests.profile_factory import typed_profile


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
            yaml.dump(typed_profile(data), f)

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
                "name",
                "description",
                "tools",
                "disallowedTools",
                "model",
                "permissionMode",
                "maxTurns",
                "skills",
                "mcpServers",
                "hooks",
                "memory",
                "background",
                "effort",
                "isolation",
                "color",
                "initialPrompt",
                "prompt",
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
                "name",
                "description",
                "tools",
                "disallowedTools",
                "model",
                "maxTurns",
                "mcpServers",
                "hooks",
                "background",
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
            "tool_policy": "inherit_only",
            "supported_fields": [
                "name",
                "description",
                "model",
                "model_reasoning_effort",
                "sandbox_mode",
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
        assert adapter.resolve_capability("shell_exec").tool == "Bash"
        assert adapter.resolve_capability("agent_dispatch").tool == "Agent"

    def test_cursor_tools(self, project_dir: Path) -> None:
        adapter = get_adapter("cursor", project_dir / ".cataforge" / "platforms")
        assert adapter.resolve_capability("file_edit").tool == "Write"
        assert adapter.resolve_capability("shell_exec").tool == "Shell"
        assert adapter.resolve_capability("agent_dispatch").tool == "Task"


class TestExtendedCapabilities:
    def test_claude_code_extended(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        assert adapter.resolve_capability("notebook_edit").tool == "NotebookEdit"
        assert adapter.resolve_capability("browser_preview").tool == "preview_start"
        assert adapter.resolve_capability("code_review").status == "unsupported"

    def test_full_tool_map_includes_extended(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        assert adapter.capability_ids() >= {"file_read", "notebook_edit"}
        assert adapter.resolve_capability("file_read").tool == "Read"
        assert adapter.resolve_capability("notebook_edit").tool == "NotebookEdit"

    def test_resolve_capability_includes_extended(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        assert adapter.resolve_capability("notebook_edit").tool == "NotebookEdit"
        assert adapter.resolve_capability("code_review").status == "unsupported"

    def test_codex_extended(self, project_dir: Path) -> None:
        adapter = get_adapter("codex", project_dir / ".cataforge" / "platforms")
        assert adapter.resolve_capability("image_input").tool == "image"
        assert adapter.resolve_capability("code_review").tool == "review"

    def test_empty_extended_capabilities(self, project_dir: Path) -> None:
        adapter = get_adapter("opencode", project_dir / ".cataforge" / "platforms")
        assert adapter.resolve_capability("image_input").tool == "image"
        assert adapter.resolve_capability("notebook_edit").status == "unsupported"


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
    def test_hook_template_pins_deploying_interpreter(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        template = adapter.get_hook_command_template()
        quoted_interp = f'"{Path(sys.executable).as_posix()}"'
        assert template.startswith(f"{quoted_interp} ")
        cmd = template.format(module="guard_dangerous")
        assert cmd == (f"{quoted_interp} -m cataforge.runtime.hook.scripts.guard_dangerous")

    def test_all_platforms_share_same_template(self, project_dir: Path) -> None:
        platforms_dir = project_dir / ".cataforge" / "platforms"
        expected = (
            f'"{Path(sys.executable).as_posix()}" -m cataforge.runtime.hook.scripts.{{module}}'
        )
        for pid in ("claude-code", "cursor", "opencode"):
            adapter = get_adapter(pid, platforms_dir)
            assert adapter.get_hook_command_template() == expected


class TestClaudeCodeAgentLayout:
    """Regression guard: Claude Code uses a flat ``<name>.md`` layout only."""

    def _make_source(self, root: Path) -> Path:
        src = root / ".cataforge" / "agents"
        src.mkdir(parents=True)
        (src / "orchestrator").mkdir()
        (src / "orchestrator" / "AGENT.md").write_text(
            "---\nname: orchestrator\ndescription: Test\n---\n# body\n",
            encoding="utf-8",
        )
        return src

    def test_claude_code_emits_flat_layout_only(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        src = self._make_source(project_dir)
        actions = steps.deploy_agents(adapter, src, project_dir, dry_run=False)

        flat = project_dir / ".claude" / "agents" / "orchestrator.md"
        nested = project_dir / ".claude" / "agents" / "orchestrator" / "AGENT.md"
        assert flat.is_file(), "flat <name>.md required for native discovery"
        assert not nested.exists(), "legacy <name>/AGENT.md must no longer be written"
        assert "name: orchestrator" in flat.read_text(encoding="utf-8")
        assert any("orchestrator" in a for a in actions)

    def test_claude_code_prunes_flat_on_removal(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        src = self._make_source(project_dir)
        steps.deploy_agents(adapter, src, project_dir, dry_run=False)

        import shutil

        shutil.rmtree(src / "orchestrator")
        steps.deploy_agents(adapter, src, project_dir, dry_run=False)

        assert not (project_dir / ".claude" / "agents" / "orchestrator.md").exists()

    def test_claude_code_prunes_legacy_subdir_on_deploy(self, project_dir: Path) -> None:
        """Upgrading users: a pre-existing ``<name>/AGENT.md`` subdir left from
        the old dual layout must be cleaned up on the next deploy, even when
        the agent still exists in source."""
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        src = self._make_source(project_dir)

        legacy_dir = project_dir / ".claude" / "agents" / "orchestrator"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "AGENT.md").write_text(
            "---\nname: orchestrator\n---\nstale\n", encoding="utf-8"
        )

        steps.deploy_agents(adapter, src, project_dir, dry_run=False)

        assert not legacy_dir.exists()
        assert (project_dir / ".claude" / "agents" / "orchestrator.md").is_file()


@pytest.fixture()
def project_dir_with_tier_map(project_dir: Path) -> Path:
    """Augment project_dir profiles with model_routing.tier_map for tier tests."""
    platforms_dir = project_dir / ".cataforge" / "platforms"
    tiers = {
        "claude-code": {
            "tier_map": {"light": "haiku", "standard": "sonnet", "heavy": "opus"},
            "user_resolved": False,
        },
        "cursor": {
            "tier_map": {"light": "sonnet", "standard": "sonnet", "heavy": "opus"},
            "user_resolved": False,
        },
        "codex": {
            "tier_map": {"light": "gpt-5.3-codex-spark", "standard": "gpt-5.4", "heavy": "gpt-5.4"},
            "user_resolved": False,
        },
        "opencode": {
            "tier_map": {},
            "user_resolved": True,
        },
    }
    for pid, extra in tiers.items():
        profile_path = platforms_dir / pid / "profile.yaml"
        with open(profile_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        routing = data.setdefault("model_routing", {})
        routing.update(extra)
        with open(profile_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
    return project_dir


class TestModelTierResolution:
    """resolve_agent_model() drops the field correctly per platform."""

    def test_claude_code_resolves_to_native(self, project_dir_with_tier_map: Path) -> None:
        adapter = get_adapter("claude-code", project_dir_with_tier_map / ".cataforge" / "platforms")
        assert adapter.resolve_agent_model("light") == "haiku"
        assert adapter.resolve_agent_model("standard") == "sonnet"
        assert adapter.resolve_agent_model("heavy") == "opus"

    def test_inherit_returns_none(self, project_dir_with_tier_map: Path) -> None:
        adapter = get_adapter("claude-code", project_dir_with_tier_map / ".cataforge" / "platforms")
        assert adapter.resolve_agent_model("inherit") is None
        assert adapter.resolve_agent_model("none") is None
        assert adapter.resolve_agent_model(None) is None

    def test_codex_per_agent_false_returns_none(self, project_dir_with_tier_map: Path) -> None:
        adapter = get_adapter("codex", project_dir_with_tier_map / ".cataforge" / "platforms")
        assert adapter.resolve_agent_model("standard") is None
        assert adapter.resolve_agent_model("heavy") is None

    def test_opencode_user_resolved_returns_none(self, project_dir_with_tier_map: Path) -> None:
        adapter = get_adapter("opencode", project_dir_with_tier_map / ".cataforge" / "platforms")
        assert adapter.resolve_agent_model("standard") is None


class TestCodexDeployIntegration:
    """Codex deploy uses the canonical translator → consistent filtering."""

    def _make_source(self, root: Path) -> Path:
        src = root / ".cataforge" / "agents"
        src.mkdir(parents=True, exist_ok=True)
        (src / "implementer").mkdir()
        (src / "implementer" / "AGENT.md").write_text(
            "---\nname: implementer\n"
            "description: TDD GREEN\n"
            "tools: file_read, shell_exec\n"
            "disallowedTools: agent_dispatch\n"
            "allowed_paths:\n  - src/\n  - tests/\n"
            "skills:\n  - foo\n"
            "model_tier: standard\n"
            "maxTurns: 60\n"
            "---\n# body\n",
            encoding="utf-8",
        )
        return src

    def test_codex_drops_per_agent_fields(self, project_dir_with_tier_map: Path) -> None:
        """Codex supported_fields = [name, description, model, ...] →
        tools/disallowedTools/skills/maxTurns/allowed_paths/model_tier all dropped.
        per_agent_model=false → no `model =` line either."""
        adapter = get_adapter("codex", project_dir_with_tier_map / ".cataforge" / "platforms")
        src = self._make_source(project_dir_with_tier_map)

        steps.deploy_agents(adapter, src, project_dir_with_tier_map, dry_run=False)

        toml_path = project_dir_with_tier_map / ".codex" / "agents" / "implementer.toml"
        assert toml_path.is_file()
        content = toml_path.read_text(encoding="utf-8")

        # Universal fields kept.
        assert 'name = "implementer"' in content
        assert "description" in content
        # Frontmatter-internal & unsupported-by-codex fields dropped.
        assert "tools = " not in content
        assert "disallowedTools" not in content
        assert "skills = " not in content
        # Degradation contract: skill context survives as read-first pointers.
        assert ".cataforge/skills/" in content
        assert "maxTurns" not in content
        assert "allowed_paths" not in content
        assert "model_tier" not in content
        # per_agent_model=false → no model line.
        assert "model = " not in content


class TestAllowDenyToolCollision:
    """Mixed decisions in one native-tool equivalence class fail closed."""

    def test_cursor_collision_fails_translation(self, project_dir: Path) -> None:
        # cursor maps both file_edit and file_write → Write.
        from cataforge.runtime.agent.translator import translate_agent_md

        adapter = get_adapter("cursor", project_dir / ".cataforge" / "platforms")
        content = (
            "---\nname: a\ndescription: d\n"
            "tools: file_write\n"
            "disallowedTools: file_edit\n"
            "---\n# body\n"
        )
        with pytest.raises(ValueError, match="mixed allow/deny"):
            translate_agent_md(content, adapter)

    def test_no_collision_no_warning(self, project_dir: Path) -> None:
        from cataforge.runtime.agent.translator import translate_agent_md

        adapter = get_adapter("cursor", project_dir / ".cataforge" / "platforms")
        content = (
            "---\nname: a\ndescription: d\n"
            "tools: file_read\n"
            "disallowedTools: shell_exec\n"
            "---\n# body\n"
        )
        warnings: list[str] = []
        translate_agent_md(content, adapter, warnings_collector=warnings)
        assert not warnings

    def test_codex_inherit_only_reports_once_without_collision(self, project_dir: Path) -> None:
        adapter = get_adapter("codex", project_dir / ".cataforge" / "platforms")
        src = project_dir / ".cataforge" / "agents"
        for name in ("one", "two"):
            agent = src / name
            agent.mkdir(parents=True)
            (agent / "AGENT.md").write_text(
                "---\n"
                f"name: {name}\n"
                "description: d\n"
                "tools: file_read, shell_exec\n"
                "disallowedTools: web_fetch\n"
                "---\n# body\n",
                encoding="utf-8",
            )

        actions = steps.deploy_agents(adapter, src, project_dir)
        policy_warnings = [
            line for line in actions if "per-agent tool policy is unenforced" in line
        ]
        assert len(policy_warnings) == 1
        assert "2 agent(s)" in policy_warnings[0]


class TestSecuritySensitiveFieldDrop:
    """Dropping permissionMode on a platform that doesn't support it must
    surface a WARN — a high-privilege declaration silently lost otherwise."""

    @pytest.mark.parametrize("platform", ["cursor", "codex", "opencode"])
    def test_permission_mode_drop_warns(self, project_dir: Path, platform: str) -> None:
        from cataforge.runtime.agent.translator import translate_agent_md

        adapter = get_adapter(platform, project_dir / ".cataforge" / "platforms")
        # Sanity: none of these declare permissionMode support.
        assert "permissionMode" not in adapter.agent_supported_fields
        content = "---\nname: a\ndescription: d\npermissionMode: bypassPermissions\n---\n# body\n"
        warnings: list[str] = []
        out = translate_agent_md(content, adapter, warnings_collector=warnings)

        # Field is gone from the deployed file ...
        assert "permissionMode" not in out
        # ... but its removal is announced.
        assert warnings, f"expected a dropped-field warning on {platform}, got none"
        assert any("permissionMode" in w for w in warnings)

    def test_supported_permission_mode_not_warned(self, project_dir: Path) -> None:
        # claude-code declares permissionMode → kept, no warning.
        from cataforge.runtime.agent.translator import translate_agent_md

        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        content = "---\nname: a\ndescription: d\npermissionMode: bypassPermissions\n---\n# body\n"
        warnings: list[str] = []
        out = translate_agent_md(content, adapter, warnings_collector=warnings)
        assert "permissionMode: bypassPermissions" in out
        assert not warnings

    def test_deploy_surfaces_field_drop_in_actions(self, project_dir: Path) -> None:
        """The dropped-field WARN reaches the deployer's action log, not just
        the in-memory collector."""
        adapter = get_adapter("opencode", project_dir / ".cataforge" / "platforms")
        src = project_dir / ".cataforge" / "agents"
        (src / "guard").mkdir(parents=True)
        (src / "guard" / "AGENT.md").write_text(
            "---\nname: guard\ndescription: d\npermissionMode: bypassPermissions\n---\n# body\n",
            encoding="utf-8",
        )
        actions = steps.deploy_agents(adapter, src, project_dir, dry_run=False)
        assert any("permissionMode" in a and "WARN" in a for a in actions), (
            f"deploy actions missing permissionMode drop WARN: {actions}"
        )


class TestNativeMcpPayload:
    """Adapters render the neutral {transport, url} MCP payload into their own
    native shape; the per-platform spelling lives here, not in the spec."""

    NEUTRAL = {"transport": "http", "url": "http://localhost:9001/mcp/stream"}

    def test_claude_code_emits_type_http(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        adapter.write_mcp_config("penpot", dict(self.NEUTRAL), project_dir)
        entry = json.loads((project_dir / ".mcp.json").read_text(encoding="utf-8"))
        assert entry["mcpServers"]["penpot"] == {
            "type": "http",
            "url": "http://localhost:9001/mcp/stream",
        }

    def test_cursor_emits_url_only(self, project_dir: Path) -> None:
        adapter = get_adapter("cursor", project_dir / ".cataforge" / "platforms")
        adapter.write_mcp_config("penpot", dict(self.NEUTRAL), project_dir)
        entry = json.loads((project_dir / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        assert entry["mcpServers"]["penpot"] == {"url": "http://localhost:9001/mcp/stream"}

    def test_stdio_payload_passes_through(self, project_dir: Path) -> None:
        adapter = get_adapter("claude-code", project_dir / ".cataforge" / "platforms")
        stdio = {"command": "python", "args": ["-m", "srv"]}
        adapter.write_mcp_config("local", dict(stdio), project_dir)
        entry = json.loads((project_dir / ".mcp.json").read_text(encoding="utf-8"))
        assert entry["mcpServers"]["local"] == stdio


class TestPenpotCrossPlatformEndpoint:
    """End-to-end: the Penpot spec's url_env resolves to a LITERAL url in every
    platform's config — no ${VAR} placeholder that non-Claude platforms (Codex
    TOML, OpenCode) cannot expand."""

    _TARGETS = [
        ("claude-code", ".mcp.json"),
        ("cursor", ".cursor/mcp.json"),
        ("codex", ".codex/config.toml"),
        ("opencode", "opencode.json"),
    ]

    def _deploy(self, project_dir: Path, plat: str, rel: str) -> str:
        from cataforge.runtime.mcp.registry import MCPRegistry

        adapter = get_adapter(plat, project_dir / ".cataforge" / "platforms")
        payload = MCPRegistry(project_dir).get_platform_config("penpot", plat)
        adapter.write_mcp_config("penpot", payload, project_dir)
        return (project_dir / rel).read_text(encoding="utf-8")

    def test_self_hosted_default_is_literal_on_every_platform(
        self, project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from cataforge.adapter.integrations.penpot.mcp_spec import write_penpot_mcp_spec

        write_penpot_mcp_spec(project_dir)
        monkeypatch.delenv("PENPOT_MCP_URL", raising=False)
        for plat, rel in self._TARGETS:
            text = self._deploy(project_dir, plat, rel)
            assert "${" not in text, f"{plat} config carries an unexpanded placeholder: {text}"
            assert "http://localhost:9001/mcp/stream" in text

    def test_env_override_writes_literal_token_url_on_every_platform(
        self, project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from cataforge.adapter.integrations.penpot.mcp_spec import write_penpot_mcp_spec

        write_penpot_mcp_spec(project_dir)
        hosted = "https://design.penpot.app/mcp/stream?userToken=k"
        monkeypatch.setenv("PENPOT_MCP_URL", hosted)
        for plat, rel in self._TARGETS:
            text = self._deploy(project_dir, plat, rel)
            assert hosted in text, f"{plat} config missing resolved hosted url: {text}"
            assert "${" not in text
