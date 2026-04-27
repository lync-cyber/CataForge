"""``cataforge-plugin.yaml`` manifest validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    id: str
    name: str = ""
    version: str = "0.0.0"
    description: str = ""
    cataforge_version: str = ">=0.1.0"
    author: str = ""

    provides_skills: list[str] = Field(default_factory=list)
    provides_mcp_servers: list[str] = Field(default_factory=list)
    provides_hooks: list[dict[str, Any]] = Field(default_factory=list)
    provides_agents: list[str] = Field(default_factory=list)

    requires_commands: list[str] = Field(default_factory=list)
    requires_pip: list[str] = Field(default_factory=list)
    requires_npm: list[str] = Field(default_factory=list)

    platforms: dict[str, str] = Field(default_factory=dict)
    source_path: Path | None = None

    @classmethod
    def from_yaml_file(cls, path: Path) -> PluginManifest:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or "id" not in data:
            raise ValueError(f"Invalid plugin manifest: missing 'id' in {path.name}")
        provides = data.get("provides", {})
        requires = data.get("requires", {})
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            version=data.get("version", "0.0.0"),
            description=data.get("description", ""),
            cataforge_version=data.get("cataforge_version", ">=0.1.0"),
            author=data.get("author", ""),
            provides_skills=provides.get("skills", []),
            provides_mcp_servers=provides.get("mcp_servers", []),
            provides_hooks=provides.get("hooks", []),
            provides_agents=provides.get("agents", []),
            requires_commands=requires.get("commands", []),
            requires_pip=requires.get("pip", []),
            requires_npm=requires.get("npm", []),
            platforms=data.get("platforms", {}),
            source_path=path.parent,
        )
