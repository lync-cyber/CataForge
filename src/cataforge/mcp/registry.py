"""MCP unified registry — declarative registration and discovery.

Supports three registration methods (priority descending):
1. Declarative: .cataforge/mcp/*.yaml spec files
2. Convention: pyproject.toml entry_points "cataforge.mcp"
3. Programmatic: registry.register(MCPServerSpec(...))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.schema.mcp_spec import MCPServerSpec, MCPServerState

logger = logging.getLogger("cataforge.mcp")


class MCPRegistry:
    """Central MCP server registry."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._paths = ProjectPaths(project_root or find_project_root())
        self._servers: dict[str, MCPServerSpec] = {}
        self._states: dict[str, MCPServerState] = {}
        self._scan_declarative()
        self._scan_entry_points()

    def _scan_declarative(self) -> None:
        """Scan .cataforge/mcp/ for YAML server specs."""
        mcp_dir = self._paths.mcp_dir
        if not mcp_dir.is_dir():
            return

        for yaml_file in sorted(mcp_dir.glob("*.yaml")):
            try:
                spec = self._parse_spec_file(yaml_file)
                self._servers[spec.id] = spec
                self._states[spec.id] = MCPServerState(spec_id=spec.id)
            except Exception as e:
                logger.warning("Skipping invalid MCP spec %s: %s", yaml_file.name, e)

    def _scan_entry_points(self) -> None:
        """Scan pip-installed packages for cataforge.mcp entry points."""
        try:
            from importlib.metadata import entry_points

            eps = entry_points(group="cataforge.mcp")
            for ep in eps:
                try:
                    factory = ep.load()
                    if callable(factory):
                        spec = factory()
                        if isinstance(spec, MCPServerSpec):
                            self._servers.setdefault(spec.id, spec)
                            self._states.setdefault(
                                spec.id, MCPServerState(spec_id=spec.id)
                            )
                except Exception as e:
                    logger.warning("Skipping MCP entry_point %s: %s", ep.name, e)
        except Exception as e:
            logger.debug("entry_points scan unavailable: %s", e)

    def _parse_spec_file(self, path: Path) -> MCPServerSpec:
        """Parse a YAML spec file into MCPServerSpec."""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict) or "id" not in data:
            raise ValueError(f"Invalid MCP spec: missing 'id' in {path.name}")

        return MCPServerSpec.model_validate(data)

    def register(self, spec: MCPServerSpec) -> None:
        """Programmatically register an MCP server."""
        self._servers[spec.id] = spec
        if spec.id not in self._states:
            self._states[spec.id] = MCPServerState(spec_id=spec.id)

    def register_from_file(self, path: str | Path) -> MCPServerSpec:
        """Register from a YAML spec file path."""
        spec = self._parse_spec_file(Path(path))
        self.register(spec)
        return spec

    def list_servers(self) -> list[MCPServerSpec]:
        return list(self._servers.values())

    def get_server(self, server_id: str) -> MCPServerSpec | None:
        return self._servers.get(server_id)

    def get_state(self, server_id: str) -> MCPServerState | None:
        return self._states.get(server_id)

    def get_platform_config(self, server_id: str, platform_id: str) -> dict[str, Any]:
        """Get the MCP config payload for a specific platform."""
        spec = self._servers.get(server_id)
        if spec is None:
            return {}

        base: dict[str, Any] = {
            "command": spec.command,
            "args": spec.args,
        }
        if spec.env:
            base["env"] = spec.env

        platform_override = spec.platform_config.get(platform_id, {})
        base.update(platform_override)
        return base
