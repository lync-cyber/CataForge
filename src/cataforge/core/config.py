"""Unified configuration management — single source of truth.

Fixes C-1: eliminates the `.claude/framework.json` vs `.cataforge/framework.json` split.
All config reads go through this module.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.schema.framework import FrameworkFile

logger = logging.getLogger("cataforge.config")


class ConfigManager:
    """Access to framework.json and derived constants.

    Primarily read-only; ``set_runtime_platform`` is the only supported
    write operation (persists ``runtime.platform`` back to disk).
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self._paths = ProjectPaths(project_root or find_project_root())
        self._cache: dict[str, Any] | None = None

    @property
    def paths(self) -> ProjectPaths:
        return self._paths

    # ---- framework.json ----

    def load(self) -> dict[str, Any]:
        """Load and cache the full framework.json."""
        if self._cache is not None:
            return self._cache
        path = self._paths.framework_json
        if not path.is_file():
            self._cache = {}
            return self._cache
        raw = json.loads(path.read_text(encoding="utf-8"))
        try:
            self._cache = FrameworkFile.model_validate(raw).model_dump(
                mode="json", exclude_none=False
            )
        except ValidationError as e:
            logger.warning("framework.json validation failed, using raw JSON: %s", e)
            self._cache = raw
        return self._cache

    def reload(self) -> dict[str, Any]:
        """Force re-read from disk."""
        self._cache = None
        return self.load()

    # ---- convenience accessors ----

    @property
    def version(self) -> str:
        return str(self.load().get("version", "0.0.0"))

    @property
    def runtime_platform(self) -> str:
        return str(self.load().get("runtime", {}).get("platform", "claude-code"))

    @property
    def constants(self) -> dict[str, Any]:
        return dict(self.load().get("constants", {}))

    def get_constant(self, name: str, default: Any = None) -> Any:
        return self.constants.get(name, default)

    @property
    def features(self) -> dict[str, Any]:
        return dict(self.load().get("features", {}))

    def is_feature_enabled(self, feature_id: str) -> bool:
        feat = self.features.get(feature_id)
        if feat is None:
            return False
        return bool(feat.get("auto_enable", False))

    @property
    def upgrade_source(self) -> dict[str, Any]:
        return dict(self.load().get("upgrade", {}).get("source", {}))

    # ---- save helpers ----

    def set_runtime_platform(self, platform_id: str) -> None:
        """Update runtime.platform in framework.json."""
        data = self.load()
        data.setdefault("runtime", {})["platform"] = platform_id
        self._write(data)

    def _write(self, data: dict[str, Any]) -> None:
        self._paths.framework_json.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self._cache = data
