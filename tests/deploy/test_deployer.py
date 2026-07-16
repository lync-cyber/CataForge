"""Regression tests for deployer platform refactor."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from cataforge.adapter.platform.registry import clear_cache
from cataforge.core.config import ConfigManager
from cataforge.runtime.deploy.deployer import Deployer


def _write_profile(base: Path, platform_id: str, profile: dict) -> None:
    p = base / ".cataforge" / "platforms" / platform_id
    p.mkdir(parents=True, exist_ok=True)
    (p / "profile.yaml").write_text(yaml.safe_dump(profile), encoding="utf-8")


def _init_project(tmp_path: Path) -> Path:
    root = tmp_path
    cf = root / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "cursor"}}), encoding="utf-8"
    )
    (cf / "PROJECT-STATE.md").write_text("运行时: {platform}\n", encoding="utf-8")
    (cf / "rules").mkdir()
    (cf / "rules" / "COMMON-RULES.md").write_text("# common\n", encoding="utf-8")
    (cf / "agents").mkdir()
    (cf / "agents" / "orchestrator").mkdir()
    (cf / "agents" / "orchestrator" / "AGENT.md").write_text(
        "---\nname: orchestrator\ntools: file_read\n---\ntext\n",
        encoding="utf-8",
    )
    (cf / "hooks").mkdir()
    (cf / "hooks" / "hooks.yaml").write_text(
        "hooks: {}\ndegradation_templates: {}\n", encoding="utf-8"
    )
    (cf / "mcp").mkdir()
    (cf / "mcp" / "demo.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "demo",
                "name": "demo",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@demo/mcp"],
            }
        ),
        encoding="utf-8",
    )
    return root


def test_claude_mcp_uses_project_mcp_json(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    _write_profile(
        root,
        "claude-code",
        {
            "platform_id": "claude-code",
            "display_name": "Claude Code",
            "tool_map": {"file_read": "Read"},
            "agent_definition": {
                "format": "yaml-frontmatter",
                "scan_dirs": [".claude/agents"],
                "needs_deploy": False,
            },
            "instruction_file": {
                "reads_claude_md": False,
                "targets": [{"type": "project_state_copy", "path": "CLAUDE.md"}],
            },
            "dispatch": {"tool_name": "Agent", "is_async": False},
            "hooks": {
                "config_format": None,
                "config_path": None,
                "event_map": {},
                "degradation": {},
            },
        },
    )
    clear_cache()
    cfg = ConfigManager(root)
    deployer = Deployer(cfg)
    deployer.deploy("claude-code")

    mcp_json = root / ".mcp.json"
    assert mcp_json.is_file()
    data = json.loads(mcp_json.read_text(encoding="utf-8"))
    assert "demo" in data["mcpServers"]
    settings_path = root / ".claude" / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        assert "mcpServers" not in settings


def test_codex_deploy_writes_agents_md_not_toml_agents(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    _write_profile(
        root,
        "codex",
        {
            "platform_id": "codex",
            "display_name": "Codex",
            "tool_map": {"file_read": "shell"},
            "agent_definition": {
                "format": "toml",
                "scan_dirs": [".codex/agents"],
                "needs_deploy": False,
            },
            "instruction_file": {
                "reads_claude_md": False,
                "targets": [{"type": "project_state_copy", "path": "AGENTS.md"}],
            },
            "dispatch": {"tool_name": "spawn_agent", "is_async": True},
            "hooks": {
                "config_format": None,
                "config_path": None,
                "event_map": {},
                "degradation": {},
            },
        },
    )
    clear_cache()
    cfg = ConfigManager(root)
    deployer = Deployer(cfg)
    deployer.deploy("codex")

    assert (root / "AGENTS.md").is_file()
    assert not (root / ".codex" / "agents").exists()
    config_toml = (root / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.demo]" in config_toml


def test_opencode_deploy_uses_native_agent_directory(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    _write_profile(
        root,
        "opencode",
        {
            "platform_id": "opencode",
            "display_name": "OpenCode",
            "tool_map": {"file_read": "read"},
            "agent_definition": {
                "format": "yaml-frontmatter",
                "scan_dirs": [".opencode/agents", ".claude/agents"],
                "needs_deploy": True,
            },
            "instruction_file": {
                "reads_claude_md": False,
                "targets": [{"type": "project_state_copy", "path": "AGENTS.md"}],
            },
            "dispatch": {"tool_name": "task", "is_async": False},
            "hooks": {
                "config_format": None,
                "config_path": None,
                "event_map": {},
                "degradation": {},
            },
        },
    )
    clear_cache()
    cfg = ConfigManager(root)
    deployer = Deployer(cfg)
    deployer.deploy("opencode")

    assert (root / ".opencode" / "agents" / "orchestrator.md").is_file()
    opencode_json = json.loads((root / "opencode.json").read_text(encoding="utf-8"))
    assert opencode_json["instructions"] == ["AGENTS.md", ".cataforge/rules/*.md"]
    assert "demo" in opencode_json["mcp"]


_GUARD_CMD = (
    f'"{Path(sys.executable).as_posix()}" -m cataforge.runtime.hook.scripts.guard_dangerous'
)
# Stale deployed spelling (bare ``python``) that a redeploy must replace.
_GUARD_CMD_STALE = "python -m cataforge.runtime.hook.scripts.guard_dangerous"
_BOOTSTRAP_CMD = "$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.sh"


def _claude_hooks_profile() -> dict:
    return {
        "platform_id": "claude-code",
        "display_name": "Claude Code",
        "tool_map": {"file_read": "Read", "shell_exec": "Bash"},
        "agent_definition": {
            "format": "yaml-frontmatter",
            "scan_dirs": [".claude/agents"],
            "needs_deploy": False,
        },
        "instruction_file": {
            "reads_claude_md": False,
            "targets": [{"type": "project_state_copy", "path": "CLAUDE.md"}],
        },
        "dispatch": {"tool_name": "Agent", "is_async": False},
        "hooks": {
            "config_format": "json",
            "config_path": ".claude/settings.json",
            "event_map": {"PreToolUse": "PreToolUse"},
            "degradation": {},
        },
    }


def test_deploy_preserves_foreign_settings_and_hook_entries(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    (root / ".cataforge" / "hooks" / "hooks.yaml").write_text(
        "hooks:\n"
        "  PreToolUse:\n"
        "    - script: guard_dangerous\n"
        "      matcher_capability: shell_exec\n"
        "      type: block\n"
        "degradation_templates: {}\n",
        encoding="utf-8",
    )
    _write_profile(root, "claude-code", _claude_hooks_profile())

    settings_path = root / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    session_start = [{"hooks": [{"type": "command", "command": _BOOTSTRAP_CMD}]}]
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": session_start,
                    "PreToolUse": [
                        {
                            "matcher": "StaleTool",
                            "hooks": [{"type": "command", "command": _GUARD_CMD_STALE}],
                        }
                    ],
                },
                "language": "chinese",
            }
        ),
        encoding="utf-8",
    )

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    # Foreign top-level key survives.
    assert settings["language"] == "chinese"
    # Hand-authored SessionStart bootstrap survives (CataForge emits no SessionStart).
    assert settings["hooks"]["SessionStart"] == session_start
    # CataForge-owned PreToolUse is refreshed: stale matcher replaced, no duplicate.
    # The generated wrapper carries explicit platform identity.
    pre = settings["hooks"]["PreToolUse"]
    assert len(pre) == 1
    assert pre[0]["matcher"] == "Bash"
    assert pre[0]["hooks"][0]["command"] == f"{_GUARD_CMD} --cataforge-platform claude-code"


def _claude_profile_with_settings_defaults() -> dict:
    profile = _claude_hooks_profile()
    profile["settings_defaults"] = {
        "env": {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "0"},
        "defaultShell": "bash",
    }
    return profile


def test_deploy_seeds_settings_defaults(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    _write_profile(root, "claude-code", _claude_profile_with_settings_defaults())

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings["env"]["CLAUDE_CODE_USE_POWERSHELL_TOOL"] == "0"
    assert settings["defaultShell"] == "bash"


def test_deploy_settings_defaults_preserve_user_override(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    _write_profile(root, "claude-code", _claude_profile_with_settings_defaults())

    settings_path = root / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps({"env": {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "1"}, "defaultShell": "powershell"}),
        encoding="utf-8",
    )

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    # Set-if-absent: a deliberate user override survives redeploy.
    assert settings["env"]["CLAUDE_CODE_USE_POWERSHELL_TOOL"] == "1"
    assert settings["defaultShell"] == "powershell"


def test_deploy_without_settings_defaults_seeds_nothing(tmp_path: Path) -> None:
    root = _init_project(tmp_path)
    _write_profile(root, "claude-code", _claude_hooks_profile())

    clear_cache()
    Deployer(ConfigManager(root)).deploy("claude-code")

    settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "env" not in settings
    assert "defaultShell" not in settings


_REBUILD_STATE_TPL = (
    "## 项目信息\n- 技术栈: {框架/语言/工具}\n\n"
    "## 项目状态\n- 当前阶段: {x}\n\n"
    "## 文档导航\n- 导航索引: docs/.doc-index.json\n"
)


def test_rebuild_preserves_section_merge_instruction_target(tmp_path: Path) -> None:
    """--rebuild must not purge a section-merge target. If it does, the
    instruction step finds no existing file to merge into and silently writes
    the placeholder template, wiping orchestrator-owned sections."""
    root = _init_project(tmp_path)
    (root / ".cataforge" / "PROJECT-STATE.md").write_text(_REBUILD_STATE_TPL, encoding="utf-8")
    (root / ".cataforge" / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )
    _write_profile(
        root,
        "claude-code",
        {
            "platform_id": "claude-code",
            "display_name": "Claude Code",
            "tool_map": {"file_read": "Read"},
            "agent_definition": {
                "format": "yaml-frontmatter",
                "scan_dirs": [".claude/agents"],
                "needs_deploy": False,
            },
            "instruction_file": {
                "reads_claude_md": False,
                "targets": [
                    {
                        "type": "project_state_copy",
                        "path": "CLAUDE.md",
                        "update_strategy": "section-merge",
                        "section_policy": {
                            "schema": ["项目信息"],
                            "runtime": ["项目状态"],
                            "framework": ["文档导航"],
                            "user_extensible": True,
                        },
                    }
                ],
            },
            "dispatch": {"tool_name": "Agent", "is_async": False},
            "hooks": {
                "config_format": None,
                "config_path": None,
                "event_map": {},
                "degradation": {},
            },
        },
    )
    clear_cache()
    cfg = ConfigManager(root)
    Deployer(cfg).deploy("claude-code")

    claude_md = root / "CLAUDE.md"
    assert claude_md.is_file()
    # Orchestrator adds a user-extensible section section-merge must preserve.
    # It survives a redeploy only when the existing file is the merge source;
    # a purged target falls back to the placeholder template, which has no
    # such section.
    claude_md.write_text(
        claude_md.read_text(encoding="utf-8") + "\n## 我的自定义\nSENTINEL-KEEP\n",
        encoding="utf-8",
    )

    Deployer(cfg).deploy("claude-code", rebuild=True)

    after = claude_md.read_text(encoding="utf-8")
    assert "SENTINEL-KEEP" in after, "rebuild purged the section-merge target → state lost"
