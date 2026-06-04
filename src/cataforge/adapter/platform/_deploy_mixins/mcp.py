"""MCP server config injection mixin (into the platform's mcp.json)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class McpDeployMixin:
    """MCP server config injection into the platform's mcp.json."""

    def inject_mcp_config(
        self,
        server_id: str,
        server_config: dict[str, Any],
        project_root: Path,
        *,
        dry_run: bool = False,
    ) -> list[str]:
        """Write MCP server config into the platform's configuration file.

        Default: merge into a JSON file under the standard ``mcpServers.<id>``
        key via :func:`merge_json_key`.  The concrete path comes from
        :meth:`_mcp_json_path` which subclasses override.  Platforms using a
        non-JSON or non-standard layout (e.g. Codex TOML, OpenCode's per-repo
        merge) override ``inject_mcp_config`` itself instead.
        """
        from cataforge.adapter.platform.hooks_config import merge_json_key

        mcp_path = self._mcp_json_path(project_root)
        return merge_json_key(mcp_path, f"mcpServers.{server_id}", server_config, dry_run=dry_run)

    def _mcp_json_path(self, project_root: Path) -> Path:
        """Return the JSON file path the default ``inject_mcp_config`` writes to.

        Subclasses that rely on the default implementation override this
        single method; adapters with fully custom MCP layouts override
        ``inject_mcp_config`` directly and can leave this raising.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must override either inject_mcp_config() or _mcp_json_path()"
        )
