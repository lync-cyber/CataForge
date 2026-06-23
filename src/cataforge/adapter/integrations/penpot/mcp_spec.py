"""Declarative MCP server spec for downstream Penpot wiring.

``cataforge setup --with-penpot`` writes ``.cataforge/mcp/penpot.yaml``; a later
``cataforge deploy`` injects the Penpot MCP server into each platform's config
through the unified MCP registry. The spec's presence is the gate — projects
without Penpot never carry it, so deploy never wires Penpot for them.

The MCP endpoint is a ``${PENPOT_MCP_URL:-<default>}`` placeholder: a single
``PENPOT_MCP_URL`` drives both this downstream spec and the ``remote`` mode, and
any auth token rides in the env rather than the git-tracked spec. Unset, it
falls back to the streamable-HTTP path served by the self-hosted stack's
frontend nginx (``cataforge penpot deploy``), which must be running to respond.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from cataforge.adapter.integrations.penpot._constants import DEFAULT_PENPOT_PORT
from cataforge.core.paths import ProjectPaths
from cataforge.utils.atomic_write import atomic_write_text

SPEC_ID = "penpot"


def build_penpot_mcp_spec(
    penpot_port: int = DEFAULT_PENPOT_PORT, *, mcp_url: str = ""
) -> dict[str, Any]:
    """Return the declarative Penpot MCP spec as a plain dict.

    The endpoint is declared neutrally (``transport`` + ``url``); each platform
    adapter renders it into its native config shape at deploy time.

    The url is an env-expansion placeholder ``${PENPOT_MCP_URL:-<default>}`` so
    the URL stays configurable from a single source (``PENPOT_MCP_URL``) and any
    auth token rides in the env, never in the git-tracked spec. Platforms that
    expand ``${VAR}`` in their MCP config (Claude Code, Cursor) resolve it at
    runtime; the default keeps self-hosted users working with no env set. An
    explicit *mcp_url* freezes a literal URL instead of the placeholder.
    """
    url = mcp_url or f"${{PENPOT_MCP_URL:-http://localhost:{penpot_port}/mcp/stream}}"
    return {
        "id": SPEC_ID,
        "name": "Penpot",
        "description": "Penpot 设计工具 MCP — 读写设计稿（endpoint 经 PENPOT_MCP_URL 配置）",
        "transport": "http",
        "url": url,
        "category": "design",
        "optional": True,
    }


def write_penpot_mcp_spec(
    project_root: Path, *, penpot_port: int = DEFAULT_PENPOT_PORT, mcp_url: str = ""
) -> Path:
    """Write ``.cataforge/mcp/penpot.yaml`` under *project_root*; return its path."""
    target = ProjectPaths(project_root).mcp_dir / f"{SPEC_ID}.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        target,
        yaml.safe_dump(
            build_penpot_mcp_spec(penpot_port, mcp_url=mcp_url),
            sort_keys=False,
            allow_unicode=True,
        ),
    )
    return target
