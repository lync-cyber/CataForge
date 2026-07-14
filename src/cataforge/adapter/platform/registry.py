"""Platform adapter registry — discover and instantiate adapters."""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import cast

from cataforge.adapter.platform.adapter import PlatformAdapter
from cataforge.adapter.platform.profile_schema import PlatformProfile
from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.core.platform_env import platform_from_env

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
    from_env = platform_from_env()
    if from_env is not None:
        return from_env

    if framework_json_path and framework_json_path.is_file():
        try:
            from cataforge.core.platform_id import default_platform_from_config_data

            data = read_json(framework_json_path)
            declared = default_platform_from_config_data(data)
            if declared:
                return declared
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


_CURRENT_PHASE_RE = re.compile(r"^-\s*当前阶段:\s*(.+?)\s*$", re.MULTILINE)
_EXECUTION_MODE_RE = re.compile(r"^-\s*执行模式:\s*(.+?)\s*$", re.MULTILINE)


def parse_current_phase(state_text: str) -> str | None:
    """Return the instruction file's ``当前阶段`` value, or None when absent."""
    m = _CURRENT_PHASE_RE.search(state_text)
    return m.group(1).strip() if m else None


def parse_execution_mode(state_text: str) -> str | None:
    """Return the instruction file's ``执行模式`` value, or None when absent or
    still the unfilled ``{a|b|c}`` template token."""
    m = _EXECUTION_MODE_RE.search(state_text)
    if not m:
        return None
    value = m.group(1).strip()
    return value if value and "{" not in value and "|" not in value else None


def read_execution_mode(root: Path) -> str | None:
    """Resolve *root*'s instruction file and return its ``执行模式`` value.

    Returns None when the file is unreadable or carries no mode line — the
    caller decides the fallback (typically ``standard``).
    """
    path = resolve_instruction_file(root)
    try:
        text = path.read_text()
    except OSError:
        return None
    return parse_execution_mode(text)


def read_current_phase(root: Path) -> str | None:
    """Resolve *root*'s instruction file and return its ``当前阶段`` value.

    Returns None when the file is unreadable or carries no phase line — the
    caller decides the fallback. Lives here (rank-3 adapter) so both the
    interface CLI and the runtime skill runner can read the lifecycle phase
    without an upward layer import.
    """
    path = resolve_instruction_file(root)
    try:
        text = path.read_text()
    except OSError:
        return None
    return parse_current_phase(text)


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
                return cast(PlatformAdapter, adapter_cls(profile))
    except Exception as e:
        logger.debug("entry_point lookup failed for %s: %s", platform_id, e)

    raise ValueError(f"Unknown platform: {platform_id}")
