"""Platform adapter registry — discover and instantiate adapters."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from cataforge.platform.base import PlatformAdapter

logger = logging.getLogger("cataforge.platform")

_adapter_cache: dict[tuple[str, str | None], PlatformAdapter] = {}


def detect_platform(framework_json_path: Path | None = None) -> str:
    """Detect current platform from environment or framework.json.

    Priority:
    1. CATAFORGE_PLATFORM env var (explicit override)
    2. IDE-specific env var sniffing
    3. framework.json runtime.platform
    4. Default: claude-code
    """
    explicit = os.environ.get("CATAFORGE_PLATFORM")
    if explicit:
        return explicit

    if os.environ.get("CURSOR_PROJECT_DIR"):
        return "cursor"
    if os.environ.get("CODEX_HOME"):
        return "codex"
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return "claude-code"

    if framework_json_path and framework_json_path.is_file():
        import json

        try:
            data = json.loads(framework_json_path.read_text(encoding="utf-8"))
            return str(data.get("runtime", {}).get("platform", "claude-code"))
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("Cannot read framework.json for platform detection: %s", e)

    return "claude-code"


def load_profile(platform_id: str, platforms_dir: Path | None = None) -> dict[str, Any]:
    """Load a platform's profile.yaml."""
    if platforms_dir is None:
        from cataforge.core.paths import find_project_root

        platforms_dir = find_project_root() / ".cataforge" / "platforms"

    profile_path = platforms_dir / platform_id / "profile.yaml"

    try:
        import yaml

        with open(profile_path, encoding="utf-8") as f:
            return dict(yaml.safe_load(f))
    except ImportError:
        json_path = profile_path.with_suffix(".json")
        if json_path.is_file():
            import json

            return dict(json.loads(json_path.read_text(encoding="utf-8")))
        raise ImportError(f"PyYAML not available and no JSON fallback at {json_path}") from None


def get_adapter(platform_id: str, platforms_dir: Path | None = None) -> PlatformAdapter:
    """Get (or create) the adapter for the given platform."""
    cache_key = (platform_id, str(platforms_dir) if platforms_dir else None)
    if cache_key in _adapter_cache:
        return _adapter_cache[cache_key]

    profile = load_profile(platform_id, platforms_dir)
    adapter = _create_adapter(platform_id, profile)
    _adapter_cache[cache_key] = adapter
    return adapter


def clear_cache() -> None:
    _adapter_cache.clear()


def _create_adapter(platform_id: str, profile: dict[str, Any]) -> PlatformAdapter:
    """Instantiate the correct adapter class for a platform.

    Resolution order:
    1. Built-in adapters (claude-code, cursor, codex, opencode)
    2. ``cataforge.platforms`` entry-point group (pip-installed third-party)
    """
    from cataforge.platform.claude_code import ClaudeCodeAdapter
    from cataforge.platform.codex import CodexAdapter
    from cataforge.platform.cursor import CursorAdapter
    from cataforge.platform.opencode import OpenCodeAdapter

    builtin: dict[str, type[PlatformAdapter]] = {
        "claude-code": ClaudeCodeAdapter,
        "cursor": CursorAdapter,
        "codex": CodexAdapter,
        "opencode": OpenCodeAdapter,
    }
    cls = builtin.get(platform_id)
    if cls is not None:
        return cls(profile)

    # Fall back to entry-point discovery for third-party adapters
    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="cataforge.platforms")
        for ep in eps:
            if ep.name == platform_id:
                adapter_cls = ep.load()
                return adapter_cls(profile)
    except Exception as e:
        logger.debug("entry_point lookup failed for %s: %s", platform_id, e)

    raise ValueError(f"Unknown platform: {platform_id}")
