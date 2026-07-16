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
    # Codex 不向子进程注入平台专属环境变量（CODEX_HOME 指配置 home 且仅用户
    # 显式设置时存在），身份靠 --cataforge-platform flag / CATAFORGE_PLATFORM。
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return "claude-code"
    return None
