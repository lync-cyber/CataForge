"""Pydantic models for framework config and integrations."""

from cataforge.schema.framework import FrameworkFile
from cataforge.schema.mcp_spec import HealthCheckSpec, MCPServerSpec, MCPServerState
from cataforge.schema.plugin_manifest import PluginManifest

__all__ = [
    "FrameworkFile",
    "HealthCheckSpec",
    "MCPServerSpec",
    "MCPServerState",
    "PluginManifest",
]
