"""Penpot MCP spec — downstream-distributed endpoint via PENPOT_MCP_URL.

The spec carries a literal self-hosted default url plus ``url_env`` naming the
env var deploy reads to override it. The token (if any) thus rides in the env
and the resolved value lands only in the platform's gitignored MCP config, never
in the git-tracked ``.cataforge/mcp/penpot.yaml``; the literal default keeps
every platform working with no env set.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from cataforge.adapter.integrations.penpot.mcp_spec import (
    build_penpot_mcp_spec,
    write_penpot_mcp_spec,
)

SELF_HOSTED_DEFAULT = "http://localhost:9001/mcp/stream"


def test_url_is_literal_self_hosted_default_with_url_env() -> None:
    spec = build_penpot_mcp_spec()
    assert spec["url"] == SELF_HOSTED_DEFAULT
    assert spec["url_env"] == "PENPOT_MCP_URL"
    assert spec["transport"] == "http"
    assert spec["id"] == "penpot"


def test_default_url_honours_penpot_port() -> None:
    spec = build_penpot_mcp_spec(penpot_port=19001)
    assert spec["url"] == "http://localhost:19001/mcp/stream"
    assert spec["url_env"] == "PENPOT_MCP_URL"


def test_explicit_mcp_url_changes_default() -> None:
    url = "https://design.penpot.app/mcp/stream?userToken=k"
    spec = build_penpot_mcp_spec(mcp_url=url)
    assert spec["url"] == url
    assert spec["url_env"] == "PENPOT_MCP_URL"  # env still wins at deploy time


def test_default_spec_never_embeds_token() -> None:
    spec = build_penpot_mcp_spec()
    assert "userToken" not in spec["url"]
    assert spec["url"] == SELF_HOSTED_DEFAULT


def test_write_spec_round_trips(tmp_path: Path) -> None:
    target = write_penpot_mcp_spec(tmp_path)
    assert target == tmp_path / ".cataforge" / "mcp" / "penpot.yaml"
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert data["url"] == SELF_HOSTED_DEFAULT
    assert data["url_env"] == "PENPOT_MCP_URL"
    assert data["id"] == "penpot"
