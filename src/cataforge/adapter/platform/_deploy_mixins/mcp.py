"""MCP server config injection mixin — thin delegate to the runtime step."""

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
        from cataforge.runtime.deploy.steps import inject_mcp_config

        return inject_mcp_config(
            self,  # type: ignore[arg-type]
            server_id,
            server_config,
            project_root,
            dry_run=dry_run,
        )

    def mcp_json_path(self, project_root: Path) -> Path:
        """Return the JSON file path the default ``inject_mcp_config`` writes to.

        Subclasses that rely on the default implementation override this single
        method; adapters with fully custom MCP layouts override
        ``inject_mcp_config`` directly and can leave this raising.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must override either inject_mcp_config() or mcp_json_path()"
        )
