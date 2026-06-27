"""Claude Code project MCP servers are pre-enabled on deploy.

A project ``.mcp.json`` server prompts for manual approval every new
session until it is listed in ``.claude/settings.local.json#
enabledMcpjsonServers``. Deploy writes that enablement so a configured
integration (e.g. Penpot) is connected without per-session re-approval.
"""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.adapter.platform.claude_code import ClaudeCodeAdapter
from cataforge.adapter.platform.hooks_config import merge_json_list


def _settings_local(root: Path) -> dict:
    return json.loads((root / ".claude" / "settings.local.json").read_text(encoding="utf-8"))


def test_merge_json_list_unions_and_dedupes(tmp_path: Path) -> None:
    path = tmp_path / "settings.local.json"
    merge_json_list(path, "enabledMcpjsonServers", ["penpot"])
    merge_json_list(path, "enabledMcpjsonServers", ["penpot", "other"])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["enabledMcpjsonServers"] == ["penpot", "other"]


def test_merge_json_list_preserves_user_entries(tmp_path: Path) -> None:
    path = tmp_path / "settings.local.json"
    path.write_text(json.dumps({"enabledMcpjsonServers": ["mine"]}), encoding="utf-8")
    merge_json_list(path, "enabledMcpjsonServers", ["penpot"])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["enabledMcpjsonServers"] == ["mine", "penpot"]


def test_claude_code_enables_project_mcp_server(tmp_path: Path) -> None:
    adapter = ClaudeCodeAdapter.__new__(ClaudeCodeAdapter)
    actions = adapter.enable_project_mcp_server("penpot", tmp_path, dry_run=False)
    assert _settings_local(tmp_path)["enabledMcpjsonServers"] == ["penpot"]
    assert any("settings.local.json" in a for a in actions)


def test_enable_is_idempotent(tmp_path: Path) -> None:
    adapter = ClaudeCodeAdapter.__new__(ClaudeCodeAdapter)
    adapter.enable_project_mcp_server("penpot", tmp_path, dry_run=False)
    adapter.enable_project_mcp_server("penpot", tmp_path, dry_run=False)
    assert _settings_local(tmp_path)["enabledMcpjsonServers"] == ["penpot"]


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    adapter = ClaudeCodeAdapter.__new__(ClaudeCodeAdapter)
    actions = adapter.enable_project_mcp_server("penpot", tmp_path, dry_run=True)
    assert not (tmp_path / ".claude" / "settings.local.json").exists()
    assert actions and all("would" in a for a in actions)


def test_inject_mcp_config_also_enables_for_claude_code(tmp_path: Path) -> None:
    from cataforge.runtime.deploy.steps import inject_mcp_config

    adapter = ClaudeCodeAdapter.__new__(ClaudeCodeAdapter)
    payload = {"url": "http://localhost:9001/mcp/stream", "transport": "http"}
    inject_mcp_config(adapter, "penpot", payload, tmp_path, dry_run=False)
    assert (tmp_path / ".mcp.json").is_file()
    assert _settings_local(tmp_path)["enabledMcpjsonServers"] == ["penpot"]
