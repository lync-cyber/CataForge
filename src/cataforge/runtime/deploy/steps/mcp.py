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
    """Write MCP server config into the platform's configuration file.

    Default: merge into a JSON file under the standard ``mcpServers.<id>`` key
    via :func:`merge_json_key`.  The concrete path comes from
    ``adapter.mcp_json_path``.  Platforms using a non-JSON or non-standard
    layout (e.g. Codex TOML, OpenCode's per-repo merge) override
    ``inject_mcp_config`` on the adapter itself instead.
    """
    from cataforge.adapter.platform.hooks_config import merge_json_key

    mcp_path = adapter.mcp_json_path(project_root)
    return merge_json_key(mcp_path, f"mcpServers.{server_id}", server_config, dry_run=dry_run)
