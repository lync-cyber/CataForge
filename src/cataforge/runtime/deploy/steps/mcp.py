"""MCP server config injection step (into the platform's mcp.json)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cataforge.adapter.platform.adapter import PlatformAdapter


def inject_mcp_config(
    adapter: PlatformAdapter,
    server_id: str,
    server_config: dict[str, Any],
    project_root: Path,
    *,
    dry_run: bool = False,
) -> list[str]:
    """Write one MCP server config into the platform's configuration file.

    Routes to the adapter's :meth:`write_mcp_config` strategy hook. The default
    hook merges into a JSON file under ``mcpServers.<id>`` at
    ``adapter.mcp_json_path``; Codex (TOML) and OpenCode (per-repo merge)
    override the hook for their native layout.
    """
    return adapter.write_mcp_config(server_id, server_config, project_root, dry_run=dry_run)
