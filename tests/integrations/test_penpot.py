"""Unit tests for cataforge.integrations.penpot public API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import cataforge.integrations.penpot as penpot

# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------


def testget_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("PENPOT_INSTALL_DIR", "PENPOT_PORT", "PENPOT_MCP_SERVER_PORT",
                "PENPOT_MCP_PLUGIN_PORT", "PENPOT_FLAGS"):
        monkeypatch.delenv(var, raising=False)

    cfg = penpot.get_config()

    assert cfg["penpot_port"] == penpot.DEFAULT_PENPOT_PORT
    assert cfg["mcp_port"] == penpot.DEFAULT_MCP_PORT
    assert cfg["plugin_port"] == penpot.DEFAULT_PLUGIN_PORT
    assert "penpot-docker" in cfg["penpot_dir"]
    assert "enable-login-with-password" in cfg["penpot_flags"]


def testget_config_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PENPOT_PORT", "19001")
    monkeypatch.setenv("PENPOT_MCP_SERVER_PORT", "14401")
    monkeypatch.setenv("PENPOT_INSTALL_DIR", "/tmp/my-penpot")

    cfg = penpot.get_config()

    assert cfg["penpot_port"] == 19001
    assert cfg["mcp_port"] == 14401
    assert cfg["penpot_dir"] == "/tmp/my-penpot"


# ---------------------------------------------------------------------------
# _extract_secret_key
# ---------------------------------------------------------------------------


def test_extract_secret_key_reads_unquoted(tmp_path):
    cf = tmp_path / "docker-compose.yml"
    cf.write_text("- PENPOT_SECRET_KEY=abc123def456\n", encoding="utf-8")
    assert penpot._extract_secret_key(str(cf)) == "abc123def456"


def test_extract_secret_key_reads_double_quoted(tmp_path):
    cf = tmp_path / "docker-compose.yml"
    cf.write_text('- PENPOT_SECRET_KEY="mysecret"\n', encoding="utf-8")
    assert penpot._extract_secret_key(str(cf)) == "mysecret"


def test_extract_secret_key_missing_file():
    assert penpot._extract_secret_key("/no/such/file.yml") is None


# ---------------------------------------------------------------------------
# _is_penpot_container_running — docker absent / docker present
# ---------------------------------------------------------------------------


def test_is_penpot_container_running_no_docker():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert penpot._is_penpot_container_running() is False


def test_is_penpot_container_running_empty_output():
    result = MagicMock()
    result.stdout = ""
    with patch("subprocess.run", return_value=result):
        assert penpot._is_penpot_container_running() is False


def test_is_penpot_container_running_returns_true_when_output():
    result = MagicMock()
    result.stdout = "penpot-frontend-1\n"
    with patch("subprocess.run", return_value=result):
        assert penpot._is_penpot_container_running() is True


# ---------------------------------------------------------------------------
# preflight_check — docker absent path
# ---------------------------------------------------------------------------


def test_preflight_check_fails_when_docker_absent(capsys):
    with (
        patch("cataforge.integrations.penpot.has_command", return_value=False),
        patch("cataforge.integrations.penpot.docker_compose_cmd", return_value=None),
    ):
        result = penpot.preflight_check(scope="all")
    assert result is False


# ---------------------------------------------------------------------------
# deploy_penpot — docker not running → returns False
# ---------------------------------------------------------------------------


def test_deploy_penpot_returns_false_when_docker_not_running():
    config = penpot.get_config()
    with patch("cataforge.integrations.penpot.ensure_docker_running", return_value=False):
        assert penpot.deploy_penpot(config) is False


# ---------------------------------------------------------------------------
# cmd_start — compose file present, docker running
# ---------------------------------------------------------------------------


def test_cmd_start_calls_compose_up_when_file_exists(tmp_path):
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("version: '3'\n", encoding="utf-8")
    config = {
        "penpot_dir": str(tmp_path),
        "penpot_port": 9001,
        "mcp_port": 4401,
        "plugin_port": 4400,
        "penpot_flags": "enable-login-with-password",
    }
    captured_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        r = MagicMock()
        r.returncode = 0
        return r

    with (
        patch("cataforge.integrations.penpot.preflight_check", return_value=True),
        patch(
            "cataforge.integrations.penpot.docker_compose_cmd",
            return_value=["docker", "compose"],
        ),
        patch("cataforge.integrations.penpot.ensure_docker_running", return_value=True),
        patch("subprocess.run", side_effect=fake_run),
        patch("cataforge.integrations.penpot.start_mcp", return_value=True),
    ):
        rc = penpot.cmd_start(config)

    assert rc == 0
    compose_calls = [c for c in captured_cmds if "up" in c]
    assert compose_calls, "expected at least one 'up' call to docker compose"
    assert str(compose_file) in compose_calls[0]


# ---------------------------------------------------------------------------
# cmd_stop — invokes stop_mcp and compose down
# ---------------------------------------------------------------------------


def test_cmd_stop_invokes_stop_mcp_and_compose_down(tmp_path):
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("version: '3'\n", encoding="utf-8")
    config = {
        "penpot_dir": str(tmp_path),
        "penpot_port": 9001,
        "mcp_port": 4401,
        "plugin_port": 4400,
        "penpot_flags": "enable-login-with-password",
    }
    captured_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        r = MagicMock()
        r.returncode = 0
        return r

    with (
        patch("cataforge.integrations.penpot.stop_mcp", return_value=True),
        patch(
            "cataforge.integrations.penpot.docker_compose_cmd",
            return_value=["docker", "compose"],
        ),
        patch("subprocess.run", side_effect=fake_run),
    ):
        rc = penpot.cmd_stop(config)

    assert rc == 0
    down_calls = [c for c in captured_cmds if "down" in c]
    assert down_calls, "expected a compose down call"
    assert str(compose_file) in down_calls[0]


# ---------------------------------------------------------------------------
# cmd_status — reports based on running checks
# ---------------------------------------------------------------------------


def test_cmd_status_returns_zero(capsys):
    config = penpot.get_config()
    with (
        patch("cataforge.integrations.penpot._is_penpot_running", return_value=False),
        patch("cataforge.integrations.penpot._is_mcp_running", return_value=False),
        patch("cataforge.integrations.penpot.is_port_listening", return_value=False),
    ):
        rc = penpot.cmd_status(config)
    assert rc == 0


# ---------------------------------------------------------------------------
# _read_mcp_pid / _write_mcp_pid / _remove_mcp_pid round-trip
# ---------------------------------------------------------------------------


def test_mcp_pid_roundtrip(tmp_path, monkeypatch: pytest.MonkeyPatch):
    pid_file = tmp_path / "penpot-mcp-server.pid"
    monkeypatch.setattr(penpot, "MCP_PID_FILE", str(pid_file))

    assert penpot._read_mcp_pid() is None

    penpot._write_mcp_pid(12345)
    assert penpot._read_mcp_pid() == 12345

    penpot._remove_mcp_pid()
    assert penpot._read_mcp_pid() is None
