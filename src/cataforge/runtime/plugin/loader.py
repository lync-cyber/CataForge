"""Plugin discovery and loading.

Two sources (priority descending):
1. entry_points registered third-party packages (pip-installed)
2. Project-level plugins (.cataforge/plugins/)

Duplicate IDs: entry_points take precedence over project-level plugins.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.core.schema.plugin_manifest import PluginManifest

logger = logging.getLogger("cataforge.runtime.plugin")


def _load_manifest(ep: Any) -> PluginManifest | None:
    """Load one entry point and return its manifest, or None if it isn't one."""
    factory = ep.load()
    if not callable(factory):
        return None
    manifest = factory()
    return manifest if isinstance(manifest, PluginManifest) else None


class PluginLoader:
    """Discover plugins from all sources."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._paths = ProjectPaths(project_root or find_project_root())

    def discover(self) -> list[PluginManifest]:
        seen_ids: set[str] = set()
        plugins: list[PluginManifest] = []

        for p in self._scan_entry_points():
            if p.id not in seen_ids:
                seen_ids.add(p.id)
                plugins.append(p)

        for p in self._scan_project_plugins():
            if p.id not in seen_ids:
                seen_ids.add(p.id)
                plugins.append(p)

        return plugins

    # ---- resolved contributions (shared by loaders / deploy / hooks / MCP) ----

    def provided_skill_dirs(self) -> dict[str, Path]:
        """Map ``skill_id → <source_path>/skills/<id>`` for plugin skills."""
        return self._provided_asset_dirs("skills", "SKILL.md", lambda p: p.provides_skills)

    def provided_agent_dirs(self) -> dict[str, Path]:
        """Map ``agent_id → <source_path>/agents/<id>`` for plugin agents."""
        return self._provided_asset_dirs("agents", "AGENT.md", lambda p: p.provides_agents)

    def provided_hooks(self) -> list[dict[str, Any]]:
        """Flatten every plugin's ``provides.hooks`` entries (discover order)."""
        out: list[dict[str, Any]] = []
        for p in self.discover():
            out.extend(p.provides_hooks)
        return out

    def provided_mcp_spec_files(self) -> dict[str, Path]:
        """Map ``server_id → <source_path>/mcp/<id>.yaml`` for plugin MCP servers."""
        out: dict[str, Path] = {}
        for p in self.discover():
            if p.source_path is None:
                continue
            for sid in p.provides_mcp_servers:
                spec = p.source_path / "mcp" / f"{sid}.yaml"
                if spec.is_file():
                    out.setdefault(sid, spec)
        return out

    def _provided_asset_dirs(
        self,
        kind: str,
        main_file: str,
        ids_of: Callable[[PluginManifest], list[str]],
    ) -> dict[str, Path]:
        out: dict[str, Path] = {}
        for p in self.discover():
            if p.source_path is None:
                continue
            for asset_id in ids_of(p):
                d = p.source_path / kind / asset_id
                if (d / main_file).is_file():
                    out.setdefault(asset_id, d)  # first discoverer wins (entry-point > local)
        return out

    def _scan_project_plugins(self) -> list[PluginManifest]:
        """Scan .cataforge/plugins/ for local plugin manifests."""
        plugins_dir = self._paths.plugins_dir
        if not plugins_dir.is_dir():
            return []

        result: list[PluginManifest] = []
        for manifest_file in sorted(plugins_dir.glob("*/cataforge-plugin.yaml")):
            try:
                manifest = PluginManifest.from_yaml_file(manifest_file)
                result.append(manifest)
            except Exception as e:
                logger.warning("Skipping invalid plugin %s: %s", manifest_file.parent.name, e)
        return result

    def _scan_entry_points(self) -> list[PluginManifest]:
        """Scan pip-installed packages for cataforge.plugins entry points."""
        try:
            from importlib.metadata import entry_points

            eps = entry_points(group="cataforge.plugins")
        except Exception as e:
            logger.debug("entry_points scan unavailable: %s", e)
            return []
        result: list[PluginManifest] = []
        for ep in eps:
            try:
                manifest = _load_manifest(ep)
            except Exception as e:
                logger.warning("Skipping plugin entry_point %s: %s", ep.name, e)
                continue
            if manifest is not None:
                result.append(manifest)
        return result
