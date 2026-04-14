"""Claude Code platform adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cataforge.platform.base import PlatformAdapter
from cataforge.platform.helpers import merge_json_key


class ClaudeCodeAdapter(PlatformAdapter):
    @property
    def platform_id(self) -> str:
        return "claude-code"

    @property
    def display_name(self) -> str:
        return "Claude Code"

    def get_tool_map(self) -> dict[str, str | None]:
        return dict(self._profile.get("tool_map", {}))

    def get_project_root_env_var(self) -> str | None:
        return "CLAUDE_PROJECT_DIR"

    def get_agent_scan_dirs(self) -> list[str]:
        return list(self._profile.get("agent_definition", {}).get("scan_dirs", [".claude/agents"]))

    def get_agent_format(self) -> str:
        return "yaml-frontmatter"

    def inject_mcp_config(
        self,
        server_id: str,
        server_config: dict[str, Any],
        project_root: Path,
        *,
        dry_run: bool = False,
    ) -> list[str]:
        mcp_path = project_root / ".mcp.json"
        return merge_json_key(mcp_path, f"mcpServers.{server_id}", server_config, dry_run=dry_run)
