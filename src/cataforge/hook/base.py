"""Hook infrastructure — cross-platform shared utilities for hook scripts.

Provides:
- read_hook_input(): unified stdin JSON reading
- hook_main(): hook entry decorator
- get_platform(): current runtime platform ID
- matches_capability(): cross-platform tool name matching
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger("cataforge.hook")


def read_hook_input() -> dict[str, Any]:
    """Read and parse stdin JSON with robust encoding handling."""
    try:
        raw = sys.stdin.buffer.read()
        text = raw.decode("utf-8", errors="replace")
        return dict(json.loads(text))
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError, AttributeError) as e:
        logger.debug("Failed to parse hook stdin: %s", e)
        return {}


def get_platform() -> str:
    """Get the current runtime platform ID.

    Priority:
    1. CATAFORGE_PLATFORM env var
    2. IDE-specific env var detection
    3. framework.json fallback
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

    return _detect_from_framework_json()


def _detect_from_framework_json() -> str:
    fj_path = Path(__file__).resolve().parent.parent.parent.parent / ".cataforge" / "framework.json"
    if not fj_path.is_file():
        fj_path2 = _find_framework_json()
        if fj_path2:
            fj_path = fj_path2

    try:
        with open(fj_path, encoding="utf-8") as f:
            config = json.load(f)
        return str(config.get("runtime", {}).get("platform", "claude-code"))
    except (OSError, json.JSONDecodeError):
        return "claude-code"


def _find_framework_json() -> Path | None:
    """Walk up from CWD looking for .cataforge/framework.json."""
    d = Path.cwd()
    while True:
        candidate = d / ".cataforge" / "framework.json"
        if candidate.is_file():
            return candidate
        parent = d.parent
        if parent == d:
            return None
        d = parent


_tool_map_cache: dict[str, str | None] | None = None


def _load_tool_map() -> dict[str, str | None]:
    global _tool_map_cache
    if _tool_map_cache is not None:
        return _tool_map_cache

    platform_id = get_platform()
    try:
        from cataforge.platform.registry import get_adapter

        adapter = get_adapter(platform_id)
        _tool_map_cache = adapter.get_tool_map()
    except Exception as e:
        logger.debug("Failed to load tool_map from adapter, using profile fallback: %s", e)
        _tool_map_cache = _load_tool_map_from_profile(platform_id)
    return _tool_map_cache


def _load_tool_map_from_profile(platform_id: str) -> dict[str, str | None]:
    """Load tool_map directly from profile.yaml without full adapter import chain.

    Falls back to Claude Code defaults only when no profile can be found.
    """
    import json as _json

    # Try to find .cataforge/platforms/<id>/profile.yaml near the project root
    fj_path = _find_framework_json()
    if fj_path:
        profile_yaml = fj_path.parent / "platforms" / platform_id / "profile.yaml"
        try:
            import yaml

            with open(profile_yaml, encoding="utf-8") as f:
                profile = yaml.safe_load(f)
            if isinstance(profile, dict) and "tool_map" in profile:
                return dict(profile["tool_map"])
        except Exception:
            pass

        profile_json = profile_yaml.with_suffix(".json")
        if profile_json.is_file():
            try:
                raw = _json.loads(profile_json.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and "tool_map" in raw:
                    return dict(raw["tool_map"])
            except Exception:
                pass

    # Last-resort fallback: hardcoded Claude Code defaults
    logger.debug("Using hardcoded Claude Code tool_map defaults")
    return {
        "file_read": "Read",
        "file_write": "Write",
        "file_edit": "Edit",
        "file_glob": "Glob",
        "file_grep": "Grep",
        "shell_exec": "Bash",
        "web_search": "WebSearch",
        "web_fetch": "WebFetch",
        "user_question": "AskUserQuestion",
        "agent_dispatch": "Agent",
    }


def get_platform_tool_name(capability: str) -> str | None:
    return _load_tool_map().get(capability)


def matches_capability(data: dict[str, Any], capability: str) -> bool:
    """Check if the hook's stdin tool_name matches a capability."""
    tool_name = data.get("tool_name", "")
    expected = get_platform_tool_name(capability)

    if expected is None:
        return False

    if capability == "file_edit":
        edit_tools = {expected}
        write_name = get_platform_tool_name("file_write")
        if write_name:
            edit_tools.add(write_name)
        return tool_name in edit_tools

    return tool_name == expected


_DISPLAY_NAMES = {
    "claude-code": "Claude Code",
    "cursor": "Cursor",
    "codex": "Codex CLI",
    "opencode": "OpenCode",
}


def get_platform_display_name() -> str:
    return _DISPLAY_NAMES.get(get_platform(), "CataForge")


def hook_main(func: Callable[[], Any]) -> Callable[[], None]:
    """Hook entry decorator. Catches exceptions, always exits 0."""

    def wrapper() -> None:
        try:
            func()
        except SystemExit:
            raise
        except Exception as e:
            print(f"[HOOK-ERROR] {func.__module__}.{func.__name__}: {e}", file=sys.stderr)
            sys.exit(0)

    return wrapper
