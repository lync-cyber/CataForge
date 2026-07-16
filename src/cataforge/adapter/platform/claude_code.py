"""Claude Code platform adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cataforge.adapter.platform.adapter import PlatformAdapter
from cataforge.adapter.platform.mcp_config import neutral_remote_payload


class ClaudeCodeAdapter(PlatformAdapter):
    @property
    def platform_id(self) -> str:
        return "claude-code"

    @property
    def display_name(self) -> str:
        return "Claude Code"

    def get_agent_scan_dirs(self) -> list[str]:
        return list(self._profile.agent_definition.scan_dirs) or [".claude/agents"]

    def get_agent_format(self) -> str:
        return "yaml-frontmatter"

    @property
    def agent_layout(self) -> str:
        # Claude Code's native /agents command reads a flat ``<name>.md`` per
        # agent, not the source ``<name>/AGENT.md`` subdir tree.
        return "flat"

    @property
    def prune_legacy_agent_subdirs(self) -> bool:
        # Tear down ``<name>/AGENT.md`` subdirs left by a prior dual-layout deploy.
        return True

    def mcp_json_path(self, project_root: Path) -> Path:
        return project_root / ".mcp.json"

    def _native_mcp_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        # .mcp.json remote servers use {"type": "http"|"sse", "url": ...}.
        return neutral_remote_payload(payload, type_key=True)

    def enable_project_mcp_server(
        self, server_id: str, project_root: Path, *, dry_run: bool = False
    ) -> list[str]:
        # A project ``.mcp.json`` server stays unapproved (prompting every
        # session) until listed here; settings.local.json is per-user/gitignored,
        # the right home for "I trust this project's server on my machine".
        from cataforge.adapter.platform.hooks_config import merge_json_list

        settings_local = project_root / ".claude" / "settings.local.json"
        return merge_json_list(
            settings_local, "enabledMcpjsonServers", [server_id], dry_run=dry_run
        )
