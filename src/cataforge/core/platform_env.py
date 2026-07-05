"""Runtime platform detection from environment variables."""

from __future__ import annotations

import os


def platform_from_env() -> str | None:
    """Platform id from ``CATAFORGE_PLATFORM`` or an IDE-specific env var.

    Returns ``None`` when no env signal is present so callers can fall back to
    framework.json (each caller resolves that fallback differently).
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
    return None
