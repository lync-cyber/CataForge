"""Platform adapter registry — discover and instantiate adapters."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from cataforge.adapter.platform.adapter import PlatformAdapter
from cataforge.adapter.platform.profile_schema import PlatformProfile
from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json

logger = logging.getLogger("cataforge.adapter.platform")

# Built-in platform ids (SSOT). The id→class map in ``_create_adapter`` must
# cover exactly these; ``conformance.ALL_PLATFORMS`` and CLI ``--platform``
# choices derive from this tuple.
BUILTIN_PLATFORM_IDS: tuple[str, ...] = ("claude-code", "cursor", "codex", "opencode")

_adapter_cache: dict[tuple[str, str | None], PlatformAdapter] = {}
_cache_lock = threading.Lock()


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
        try:
            data = read_json(framework_json_path)
            return str(data.get("runtime", {}).get("platform", "claude-code"))
        except ConfigError as e:
            logger.debug("Cannot read framework.json for platform detection: %s", e)

    return "claude-code"


def load_profile(platform_id: str, platforms_dir: Path | None = None) -> PlatformProfile:
    """Load and validate a platform's profile.yaml.

    Malformed profiles fail here with a ``pydantic.ValidationError`` naming the
    offending field rather than surfacing as an ``AttributeError`` deep in an
    adapter property at deploy time.
    """
    if platforms_dir is None:
        from cataforge.core.paths import find_project_root

        platforms_dir = find_project_root() / ".cataforge" / "platforms"

    profile_path = platforms_dir / platform_id / "profile.yaml"

    try:
        import yaml

        with open(profile_path) as f:
            raw = yaml.safe_load(f) or {}
    except ImportError:
        json_path = profile_path.with_suffix(".json")
        if json_path.is_file():
            raw = dict(read_json(json_path))
        else:
            raise ImportError(f"PyYAML not available and no JSON fallback at {json_path}") from None

    return PlatformProfile.model_validate(raw)


def get_adapter(platform_id: str, platforms_dir: Path | None = None) -> PlatformAdapter:
    """Get (or create) the adapter for the given platform."""
    cache_key = (platform_id, str(platforms_dir) if platforms_dir else None)
    with _cache_lock:
        if cache_key in _adapter_cache:
            return _adapter_cache[cache_key]
        profile = load_profile(platform_id, platforms_dir)
        adapter = _create_adapter(platform_id, profile)
        _adapter_cache[cache_key] = adapter
        return adapter


def resolve_instruction_file(root: Path) -> Path:
    """Resolve the platform-native instruction file under *root*.

    Reads the project's platform (env override → framework.json), loads its
    adapter, and returns the first instruction target path (``CLAUDE.md`` on
    Claude Code, ``AGENTS.md`` on Cursor/Codex/OpenCode). Falls back to
    ``AGENTS.md`` when the platform declares no instruction target.
    """
    from cataforge.core.paths import ProjectPaths

    paths = ProjectPaths(root)
    platform_id = detect_platform(paths.framework_json)
    try:
        adapter = get_adapter(platform_id, paths.platforms_dir)
        for target in adapter.instruction_targets:
            rel = target.get("path")
            if rel:
                return root / str(rel)
    except (FileNotFoundError, ImportError, ConfigError):
        pass
    # Profile unreachable — fall back to the platform's conventional file.
    return root / ("CLAUDE.md" if platform_id == "claude-code" else "AGENTS.md")


def clear_cache() -> None:
    with _cache_lock:
        _adapter_cache.clear()


def _create_adapter(platform_id: str, profile: PlatformProfile) -> PlatformAdapter:
    """Instantiate the correct adapter class for a platform.

    Resolution order:
    1. Built-in adapters (claude-code, cursor, codex, opencode)
    2. ``cataforge.platforms`` entry-point group (pip-installed third-party)
    """
    from cataforge.adapter.platform.claude_code import ClaudeCodeAdapter
    from cataforge.adapter.platform.codex import CodexAdapter
    from cataforge.adapter.platform.cursor import CursorAdapter
    from cataforge.adapter.platform.opencode import OpenCodeAdapter

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
