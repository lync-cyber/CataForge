"""Penpot integration — configuration helpers."""

from __future__ import annotations

import os
from typing import Any

from cataforge.adapter.integrations.penpot._constants import (
    DEFAULT_MCP_PACKAGE_VERSION,
    DEFAULT_MCP_PORT,
    DEFAULT_PENPOT_PORT,
    DEFAULT_PENPOT_VERSION,
    DEFAULT_PLUGIN_PORT,
)


def _env_int(name: str, default: int) -> int:
    """Read an int env var, falling back to *default* when unset or empty."""
    raw = os.environ.get(name)
    return int(raw) if raw else default


def get_config() -> dict[str, Any]:
    return {
        "penpot_dir": os.environ.get(
            "PENPOT_INSTALL_DIR",
            os.path.join(os.path.expanduser("~"), "penpot-docker"),
        ),
        "penpot_port": _env_int("PENPOT_PORT", DEFAULT_PENPOT_PORT),
        "penpot_version": os.environ.get("PENPOT_VERSION", DEFAULT_PENPOT_VERSION),
        "mcp_port": _env_int("PENPOT_MCP_SERVER_PORT", DEFAULT_MCP_PORT),
        "plugin_port": _env_int("PENPOT_MCP_PLUGIN_PORT", DEFAULT_PLUGIN_PORT),
        "penpot_flags": os.environ.get(
            "PENPOT_FLAGS",
            "enable-login-with-password disable-email-verification "
            "enable-smtp enable-prepl-server disable-secure-session-cookies",
        ),
        "mcp_version": os.environ.get("PENPOT_MCP_VERSION", DEFAULT_MCP_PACKAGE_VERSION),
        # Hosted/explicit MCP endpoint for the `remote` mode and the single
        # source of truth for the downstream-distributed URL. Empty means
        # "fall back to the self-hosted local default" at spec-build time.
        "mcp_url": os.environ.get("PENPOT_MCP_URL", ""),
    }
