"""Self-hosted Penpot MCP: plugin-connection onboarding and endpoint clarity.

The container stack's MCP handshake can be Up while the browser plugin is not
connected, and the npx ports (4400/4401) are never exposed self-hosted. These
tests pin the guidance that disambiguates both so a healthy stack actually
becomes usable from the LLM side.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import cataforge.adapter.integrations.penpot as penpot


def test_self_hosted_onboarding_includes_manifest_and_endpoint(
    capsys: pytest.CaptureFixture[str],
) -> None:
    penpot.print_self_hosted_onboarding({"penpot_port": 9001})
    out = capsys.readouterr().out
    assert "http://localhost:9001/plugins/mcp/manifest.json" in out
    assert "http://localhost:9001/mcp/stream" in out
    assert "Connect to MCP server" in out


def test_self_hosted_onboarding_honours_port(capsys: pytest.CaptureFixture[str]) -> None:
    penpot.print_self_hosted_onboarding({"penpot_port": 19001})
    out = capsys.readouterr().out
    assert "http://localhost:19001/plugins/mcp/manifest.json" in out


def test_cmd_deploy_prints_self_hosted_onboarding(capsys: pytest.CaptureFixture[str]) -> None:
    config = penpot.get_config()
    with (
        patch("cataforge.adapter.integrations.penpot.commands.preflight_check", return_value=True),
        patch("cataforge.adapter.integrations.penpot.commands.deploy_penpot", return_value=True),
        patch("cataforge.adapter.integrations.penpot.commands._wait_for_mcp", return_value=True),
        patch("cataforge.adapter.integrations.penpot.commands.register_claude_mcp"),
    ):
        rc = penpot.cmd_deploy(config)
    out = capsys.readouterr().out
    assert rc == 0
    assert "/plugins/mcp/manifest.json" in out


def test_cmd_status_self_hosted_hints_plugin_when_up(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    config = {"penpot_dir": str(tmp_path), "penpot_port": 9001, "mcp_port": 4401}
    with (
        patch(
            "cataforge.adapter.integrations.penpot.commands._is_penpot_running", return_value=True
        ),
        patch("cataforge.adapter.integrations.penpot.commands._is_mcp_running", return_value=True),
        patch("os.path.isfile", side_effect=lambda p: p == str(compose)),
    ):
        rc = penpot.cmd_status(config)
    out = capsys.readouterr().out
    assert rc == 0
    assert "插件未连" in out


def test_cmd_doctor_explains_endpoint_and_plugin(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n  penpot-frontend:\n    environment:\n"
        "      - PENPOT_FLAGS=foo enable-mcp\n"
        "  penpot-mcp:\n    image: penpotapp/mcp:2.16\n",
        encoding="utf-8",
    )
    config = {"penpot_dir": str(tmp_path), "penpot_port": 9001, "mcp_port": 4401}
    with (
        patch(
            "cataforge.adapter.integrations.penpot.commands._is_penpot_running", return_value=True
        ),
        patch("cataforge.adapter.integrations.penpot.commands._is_mcp_running", return_value=True),
        patch("os.path.isfile", side_effect=lambda p: p == str(compose)),
    ):
        penpot.cmd_doctor(config)
    out = capsys.readouterr().out
    assert "9001/mcp/stream" in out
    assert "4400/4401" in out
    assert "/plugins/mcp/manifest.json" in out
