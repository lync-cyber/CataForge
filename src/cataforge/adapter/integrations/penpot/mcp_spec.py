"""Declarative MCP server spec for downstream Penpot wiring.

``cataforge setup --with-penpot`` writes ``.cataforge/mcp/penpot.yaml``; a later
``cataforge deploy`` injects the Penpot MCP server into each platform's config
through the unified MCP registry. The spec's presence is the gate — projects
without Penpot never carry it, so deploy never wires Penpot for them.

The MCP endpoint is the streamable-HTTP path served by the frontend nginx of
the self-hosted stack (``cataforge penpot deploy``); the Penpot stack must be
running for the server to respond.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from cataforge.adapter.integrations.penpot._constants import DEFAULT_PENPOT_PORT
from cataforge.core.paths import ProjectPaths
from cataforge.utils.atomic_write import atomic_write_text

SPEC_ID = "penpot"


def build_penpot_mcp_spec(penpot_port: int = DEFAULT_PENPOT_PORT) -> dict[str, Any]:
    """Return the declarative Penpot MCP spec as a plain dict.

    The endpoint is declared neutrally (``transport`` + ``url``); each platform
    adapter renders it into its native config shape at deploy time.
    """
    return {
        "id": SPEC_ID,
        "name": "Penpot",
        "description": "Penpot 设计工具 MCP — 读写设计稿（需先 cataforge penpot deploy）",
        "transport": "http",
        "url": f"http://localhost:{penpot_port}/mcp/stream",
        "category": "design",
        "optional": True,
    }


def write_penpot_mcp_spec(project_root: Path, *, penpot_port: int = DEFAULT_PENPOT_PORT) -> Path:
    """Write ``.cataforge/mcp/penpot.yaml`` under *project_root*; return its path."""
    target = ProjectPaths(project_root).mcp_dir / f"{SPEC_ID}.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        target,
        yaml.safe_dump(build_penpot_mcp_spec(penpot_port), sort_keys=False, allow_unicode=True),
    )
    return target
