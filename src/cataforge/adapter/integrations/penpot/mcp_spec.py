"""Declarative MCP server spec for downstream Penpot wiring.

``cataforge setup --with-penpot`` writes ``.cataforge/mcp/penpot.yaml``; a later
``cataforge deploy`` injects the Penpot MCP server into each platform's config
through the unified MCP registry. The spec's presence is the gate — projects
without Penpot never carry it, so deploy never wires Penpot for them.

The MCP endpoint resolves at deploy time: the spec carries a literal self-hosted
default url plus ``url_env: PENPOT_MCP_URL``; when that env var is set, deploy
writes its value (which may carry an auth token) into the platform's gitignored
MCP config, otherwise the literal default is used. A single ``PENPOT_MCP_URL``
thus drives both this downstream wiring and the ``remote`` mode, no token ever
lands in the git-tracked spec, and the literal default works on every platform
without relying on platform-specific ``${VAR}`` expansion. The default points at
the streamable-HTTP path served by the self-hosted stack's frontend nginx
(``cataforge penpot deploy``), which must be running to respond.
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

    ``url`` is a literal self-hosted default and ``url_env`` names the env var
    (``PENPOT_MCP_URL``) deploy reads to override it. The resolved value (which
    may carry an auth token) lands only in the platform's gitignored MCP config,
    never in this git-tracked spec; the literal default keeps every platform
    working with no env set, regardless of whether it expands ``${VAR}`` at
    runtime. An explicit *mcp_url* changes the default url (env still wins).
    """
    url = mcp_url or f"http://localhost:{penpot_port}/mcp/stream"
    return {
        "id": SPEC_ID,
        "name": "Penpot",
        "description": "Penpot 设计工具 MCP — 读写设计稿（endpoint 经 PENPOT_MCP_URL 配置）",
        "transport": "http",
        "url": url,
        "url_env": "PENPOT_MCP_URL",
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
