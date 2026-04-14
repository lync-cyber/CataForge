"""Regression tests for deployer platform refactor."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from cataforge.core.config import ConfigManager
from cataforge.deploy.deployer import Deployer
from cataforge.platform.registry import clear_cache


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
                "config_format": None, "config_path": None,
                "event_map": {}, "degradation": {},
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
                "config_format": None, "config_path": None,
                "event_map": {}, "degradation": {},
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
                "config_format": None, "config_path": None,
                "event_map": {}, "degradation": {},
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
