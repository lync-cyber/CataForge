"""Plugin discovery and loading.

Two sources (priority descending):
1. entry_points registered third-party packages (pip-installed)
2. Project-level plugins (.cataforge/plugins/)

Duplicate IDs: entry_points take precedence over project-level plugins.
"""

from __future__ import annotations

import logging
from pathlib import Path

from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.schema.plugin_manifest import PluginManifest

logger = logging.getLogger("cataforge.plugin")


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
            result: list[PluginManifest] = []
            for ep in eps:
                try:
                    plugin_factory = ep.load()
                    if callable(plugin_factory):
                        manifest = plugin_factory()
                        if isinstance(manifest, PluginManifest):
                            result.append(manifest)
                except Exception as e:
                    logger.warning("Skipping plugin entry_point %s: %s", ep.name, e)
            return result
        except Exception as e:
            logger.debug("entry_points scan unavailable: %s", e)
            return []
