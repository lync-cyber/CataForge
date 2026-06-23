"""Penpot MCP spec — downstream-distributed endpoint via PENPOT_MCP_URL.

The spec's url is an env-expansion placeholder so a single ``PENPOT_MCP_URL``
drives the downstream wiring and any auth token rides in the env, never in the
git-tracked ``.cataforge/mcp/penpot.yaml``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from cataforge.adapter.integrations.penpot.mcp_spec import (
    build_penpot_mcp_spec,
    write_penpot_mcp_spec,
)

PLACEHOLDER = "${PENPOT_MCP_URL:-http://localhost:9001/mcp/stream}"


def test_url_is_env_placeholder_with_self_hosted_default() -> None:
    spec = build_penpot_mcp_spec()
    assert spec["url"] == PLACEHOLDER
    assert spec["transport"] == "http"
    assert spec["id"] == "penpot"


def test_placeholder_default_honours_penpot_port() -> None:
    spec = build_penpot_mcp_spec(penpot_port=19001)
    assert spec["url"] == "${PENPOT_MCP_URL:-http://localhost:19001/mcp/stream}"


def test_explicit_mcp_url_freezes_literal() -> None:
    url = "https://design.penpot.app/mcp/stream?userToken=k"
    spec = build_penpot_mcp_spec(mcp_url=url)
    assert spec["url"] == url


def test_default_spec_never_embeds_token() -> None:
    spec = build_penpot_mcp_spec()
    assert "userToken" not in spec["url"]
    assert spec["url"].startswith("${PENPOT_MCP_URL")


def test_write_spec_round_trips_placeholder(tmp_path: Path) -> None:
    target = write_penpot_mcp_spec(tmp_path)
    assert target == tmp_path / ".cataforge" / "mcp" / "penpot.yaml"
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert data["url"] == PLACEHOLDER
    assert data["id"] == "penpot"
