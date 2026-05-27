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
# D5: HANDLERS registry replaces getattr-based dispatch
# ---------------------------------------------------------------------------


def test_handlers_registry_lists_every_cmd() -> None:
    """The HANDLERS registry must expose one entry per ``cmd_*``
    function so a future renamed handler is caught here before a
    dispatch site silently AttributeErrors."""
    expected_commands = {
        "init", "deploy", "mcp-only", "remote",
        "start", "stop", "status", "doctor", "ensure",
    }
    assert set(penpot.HANDLERS) == expected_commands
    # Every entry must be a callable that takes a single config dict.
    for name, handler in penpot.HANDLERS.items():
        assert callable(handler), f"HANDLERS[{name!r}] is not callable"


def test_handlers_match_module_cmd_functions() -> None:
    """Every HANDLERS value must be the actual ``cmd_*`` function from
    the penpot module — guards against a refactor that swaps out one
    handler without updating the dispatch table."""
    name_to_attr = {
        "init": "cmd_init",
        "deploy": "cmd_deploy",
        "mcp-only": "cmd_mcp_only",
        "remote": "cmd_remote",
        "start": "cmd_start",
        "stop": "cmd_stop",
        "status": "cmd_status",
        "doctor": "cmd_doctor",
        "ensure": "cmd_ensure",
    }
    for user_name, attr_name in name_to_attr.items():
        assert penpot.HANDLERS[user_name] is getattr(penpot, attr_name)


# ---------------------------------------------------------------------------
# C7 / C8: stop_mcp guards taskkill availability + PID file encoding
# ---------------------------------------------------------------------------


def test_stop_mcp_raises_when_taskkill_missing_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C7: on a Windows-flavoured run where ``taskkill`` is not on PATH
    (stripped image / Nano Server / some CI containers), ``stop_mcp``
    must raise a clear, actionable CataforgeError instead of
    swallowing the FileNotFoundError into the bare ``except OSError``
    and reporting success.
    """
    from cataforge.cli.errors import CataforgeError

    monkeypatch.setattr(penpot, "PLATFORM", "windows")
    monkeypatch.setattr(penpot, "_read_mcp_pid", lambda: 12345)
    monkeypatch.setattr(penpot, "_is_process_alive", lambda pid: True)
    monkeypatch.setattr(penpot.shutil, "which", lambda name: None)

    with pytest.raises(CataforgeError, match="taskkill not found"):
        penpot.stop_mcp({"mcp_port": 4401})


def test_stop_mcp_uses_taskkill_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity baseline: when taskkill IS on PATH, stop_mcp proceeds and
    invokes it. Guards against an over-eager raise on systems that have
    the binary."""
    monkeypatch.setattr(penpot, "PLATFORM", "windows")
    monkeypatch.setattr(penpot, "_read_mcp_pid", lambda: 12345)
    monkeypatch.setattr(penpot, "_is_process_alive", lambda pid: True)
    monkeypatch.setattr(
        penpot.shutil, "which",
        lambda name: r"C:\Windows\System32\taskkill.exe" if name == "taskkill" else None,
    )
    monkeypatch.setattr(penpot, "_is_mcp_running", lambda c: False)

    captured: list[list[str]] = []

    def _fake_run(cmd, **_kw):
        captured.append(list(cmd))
        return MagicMock(returncode=0)

    monkeypatch.setattr(penpot.subprocess, "run", _fake_run)

    # Should complete without raising.
    penpot.stop_mcp({"mcp_port": 4401})

    assert any(
        c and c[0] == "taskkill" and "12345" in c for c in captured
    ), f"expected a taskkill invocation; got {captured!r}"


def test_pid_file_round_trip_uses_utf8(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """C8: PID file open() calls now specify encoding=utf-8. Round-trip
    a write/read so a locale that defaults to non-UTF-8 (e.g. Windows
    cp1252) doesn't silently corrupt the value."""
    pid_file = tmp_path / "penpot-mcp-server.pid"
    monkeypatch.setattr(penpot, "MCP_PID_FILE", str(pid_file))

    penpot._write_mcp_pid(98765)
    # File content is raw ASCII digits — utf-8 / cp1252 read it the same
    # way, but the explicit encoding guards against future locale
    # changes and matches the repo-wide consistency rule.
    assert pid_file.read_bytes() == b"98765"
    assert penpot._read_mcp_pid() == 98765


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


# ---------------------------------------------------------------------------
# Wave 1 — compose template fix (Bug 1: nginx penpot-mcp upstream)
# ---------------------------------------------------------------------------


def test_compose_template_disables_mcp_routing(tmp_path) -> None:
    config = {
        "penpot_dir": str(tmp_path),
        "penpot_port": 9001,
        "penpot_flags": "enable-login-with-password",
    }
    compose_path = penpot._generate_compose_file(config, force=True)
    content = (tmp_path / "docker-compose.yml").read_text(encoding="utf-8")

    assert str(compose_path) == str(tmp_path / "docker-compose.yml")
    # disable-mcp is appended so frontend nginx skips the MCP upstream entirely
    assert "disable-mcp" in content
    # Placeholder URIs prevent nginx from hard-resolving penpot-mcp at startup
    assert "PENPOT_MCP_URI=http://127.0.0.1" in content
    assert "PENPOT_MCP_URI_WS=http://127.0.0.1" in content


# ---------------------------------------------------------------------------
# Wave 1 — start_mcp env injection (Bug 2: pnpm strict dep builds)
# ---------------------------------------------------------------------------


def test_mcp_npx_env_demotes_pnpm_strict_dep_builds() -> None:
    config = {"mcp_port": 4401, "plugin_port": 4400}
    env = penpot._mcp_npx_env(config)
    assert env["PNPM_CONFIG_STRICT_DEP_BUILDS"] == "false"
    assert env["npm_config_strict_dep_builds"] == "false"
    assert env["COREPACK_ENABLE_DOWNLOAD_PROMPT"] == "0"
    assert env["PORT"] == "4401"
    assert env["PLUGIN_PORT"] == "4400"


def test_mcp_version_is_pinned_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PENPOT_MCP_VERSION", "2.14.1")
    cfg = penpot.get_config()
    assert cfg["mcp_version"] == "2.14.1"


def test_mcp_version_defaults_to_constant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PENPOT_MCP_VERSION", raising=False)
    cfg = penpot.get_config()
    assert cfg["mcp_version"] == penpot.DEFAULT_MCP_PACKAGE_VERSION


# ---------------------------------------------------------------------------
# Wave 1 — Node version preflight
# ---------------------------------------------------------------------------


def test_node_major_parses_standard_format() -> None:
    assert penpot._node_major("v22.11.0") == 22
    assert penpot._node_major("22.11.0") == 22
    assert penpot._node_major("v20.0.0\n") == 20


def test_node_major_handles_garbage() -> None:
    assert penpot._node_major("") is None
    assert penpot._node_major("not-a-version") is None


def test_preflight_warns_on_unsupported_node(capsys) -> None:
    with (
        patch("cataforge.integrations.penpot.has_command", return_value=True),
        patch(
            "cataforge.integrations.penpot.get_command_version",
            return_value="v25.8.0",
        ),
        patch(
            "cataforge.integrations.penpot.docker_compose_cmd",
            return_value=["docker", "compose"],
        ),
    ):
        result = penpot.preflight_check(scope="all")
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    # Preflight must not fail just because Node is too new — only warn.
    assert result is True
    assert "v25.8.0" in combined or "兼容范围" in combined


def test_preflight_accepts_supported_node(capsys) -> None:
    with (
        patch("cataforge.integrations.penpot.has_command", return_value=True),
        patch(
            "cataforge.integrations.penpot.get_command_version",
            return_value="v22.11.0",
        ),
        patch(
            "cataforge.integrations.penpot.docker_compose_cmd",
            return_value=["docker", "compose"],
        ),
    ):
        result = penpot.preflight_check(scope="all")
    captured = capsys.readouterr()
    assert result is True
    assert "兼容范围" not in (captured.out + captured.err)


# ---------------------------------------------------------------------------
# Wave 1 — failure diagnoser
# ---------------------------------------------------------------------------


def test_diagnose_recognises_ignored_builds() -> None:
    log = (
        "Lockfile is up to date, resolution step is skipped\n"
        " ERR_PNPM_IGNORED_BUILDS  Ignored build scripts: esbuild@0.25.12\n"
        "Run \"pnpm approve-builds\" to pick which dependencies should be allowed.\n"
    )
    hints = penpot._diagnose_mcp_log(log)
    assert hints
    joined = "\n".join(hints)
    assert "pnpm" in joined
    assert "PNPM_CONFIG_STRICT_DEP_BUILDS" in joined


def test_diagnose_recognises_nginx_upstream() -> None:
    log = 'nginx: [emerg] host not found in upstream "penpot-mcp" in /etc/nginx/nginx.conf:145'
    hints = penpot._diagnose_mcp_log(log)
    assert hints
    assert "penpot-mcp" in "\n".join(hints)


def test_diagnose_recognises_port_in_use() -> None:
    log = "Error: listen EADDRINUSE: address already in use :::4401"
    hints = penpot._diagnose_mcp_log(log)
    assert hints
    assert "stop" in "\n".join(hints).lower() or "占用" in "\n".join(hints)


def test_diagnose_returns_empty_on_unknown_log() -> None:
    assert penpot._diagnose_mcp_log("totally unexpected output") == []


def test_tail_log_returns_last_lines(tmp_path) -> None:
    log = tmp_path / "mcp.log"
    log.write_text("\n".join(f"line {i}" for i in range(50)), encoding="utf-8")
    tail = penpot._tail_log(str(log), lines=5)
    assert tail == [f"line {i}" for i in range(45, 50)]


def test_tail_log_missing_file_returns_empty(tmp_path) -> None:
    assert penpot._tail_log(str(tmp_path / "missing.log")) == []


# ---------------------------------------------------------------------------
# Wave 2 — remote (SaaS) onboarding
# ---------------------------------------------------------------------------


def test_print_remote_onboarding_includes_manifest_and_endpoint(capsys) -> None:
    config = {"plugin_port": 4400, "mcp_port": 4401}
    penpot.print_remote_onboarding(config)
    out = capsys.readouterr().out
    assert "http://localhost:4400/manifest.json" in out
    assert "http://localhost:4401/mcp" in out
    assert "design.penpot.app" in out
    assert "Connect to MCP server" in out


def test_cmd_remote_skips_docker_preflight() -> None:
    config = penpot.get_config()
    captured: list[str] = []

    def fake_preflight(scope: str = "all") -> bool:
        captured.append(scope)
        return True

    with (
        patch("cataforge.integrations.penpot.preflight_check",
              side_effect=fake_preflight),
        patch("cataforge.integrations.penpot.start_mcp", return_value=True),
        patch("cataforge.integrations.penpot.register_claude_mcp"),
        patch("cataforge.integrations.penpot.print_remote_onboarding"),
    ):
        rc = penpot.cmd_remote(config)

    assert rc == 0
    assert captured == ["mcp"]  # NOT "all" — remote mode never touches Docker


def test_cmd_remote_fails_when_mcp_cannot_start() -> None:
    config = penpot.get_config()
    with (
        patch("cataforge.integrations.penpot.preflight_check", return_value=True),
        patch("cataforge.integrations.penpot.start_mcp", return_value=False),
    ):
        rc = penpot.cmd_remote(config)
    assert rc == 1


def test_remote_argparse_subcommand_dispatches() -> None:
    """`python -m cataforge.integrations.penpot remote` routes to the
    ``remote`` entry in ``penpot.HANDLERS``.

    Post-D5: dispatch is via the module-level ``HANDLERS`` registry, so
    patching ``penpot.cmd_remote`` no longer intercepts the call (the
    dict captured the original function reference at import time).
    Patching ``HANDLERS["remote"]`` instead expresses the new
    contract: ``main()`` must look the subcommand up in HANDLERS and
    invoke whatever it finds there.
    """
    mock = MagicMock(return_value=0)
    with (
        patch("cataforge.integrations.penpot.load_dotenv"),
        patch.dict(penpot.HANDLERS, {"remote": mock}),
    ):
        rc = penpot.main(["remote"])
    assert rc == 0
    mock.assert_called_once()


# ---------------------------------------------------------------------------
# Wave 3 — interactive init wizard
# ---------------------------------------------------------------------------


def test_cmd_init_dispatches_remote_on_choice_1(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "1")
    with patch(
        "cataforge.integrations.penpot.cmd_remote", return_value=0
    ) as mock:
        rc = penpot.cmd_init(penpot.get_config())
    assert rc == 0
    mock.assert_called_once()


def test_cmd_init_dispatches_deploy_on_choice_2(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "2")
    with patch(
        "cataforge.integrations.penpot.cmd_deploy", return_value=0
    ) as mock:
        rc = penpot.cmd_init(penpot.get_config())
    assert rc == 0
    mock.assert_called_once()


def test_cmd_init_dispatches_mcp_only_on_choice_3(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "3")
    with patch(
        "cataforge.integrations.penpot.cmd_mcp_only", return_value=0
    ) as mock:
        rc = penpot.cmd_init(penpot.get_config())
    assert rc == 0
    mock.assert_called_once()


def test_cmd_init_uses_default_on_empty_input(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    with patch(
        "cataforge.integrations.penpot.cmd_remote", return_value=0
    ) as mock:
        rc = penpot.cmd_init(penpot.get_config())
    assert rc == 0
    mock.assert_called_once()


def test_cmd_init_handles_eof_gracefully(monkeypatch) -> None:
    """EOFError → fall back to default mode (remote)."""
    def _raises(_prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", _raises)
    with patch(
        "cataforge.integrations.penpot.cmd_remote", return_value=0
    ) as mock:
        rc = penpot.cmd_init(penpot.get_config())
    assert rc == 0
    mock.assert_called_once()


# ---------------------------------------------------------------------------
# Wave 3 — table-formatted status
# ---------------------------------------------------------------------------


def test_status_rows_probes_all_three_services() -> None:
    config = {"penpot_port": 9001, "mcp_port": 4401, "plugin_port": 4400}
    with (
        patch("cataforge.integrations.penpot._is_penpot_running", return_value=True),
        patch("cataforge.integrations.penpot._is_mcp_running", return_value=False),
        patch("cataforge.integrations.penpot.is_port_listening", return_value=True),
    ):
        rows = penpot._status_rows(config)
    assert len(rows) == 3
    labels = [r[0] for r in rows]
    assert labels == ["Penpot Frontend", "MCP Server", "Plugin Server"]
    assert rows[0][1] is True   # frontend
    assert rows[1][1] is False  # mcp
    assert rows[2][1] is True   # plugin
    assert rows[0][2] == "http://localhost:9001"
    assert rows[1][2] == "http://localhost:4401/mcp"


def test_cmd_status_table_prints_next_step_when_mcp_down(capsys) -> None:
    config = penpot.get_config()
    with (
        patch("cataforge.integrations.penpot._is_penpot_running", return_value=False),
        patch("cataforge.integrations.penpot._is_mcp_running", return_value=False),
        patch("cataforge.integrations.penpot.is_port_listening", return_value=False),
    ):
        rc = penpot.cmd_status(config)
    out = capsys.readouterr().out
    assert rc == 0
    assert "cataforge penpot init" in out
    # Header bar present
    assert "Penpot 服务状态" in out


# ---------------------------------------------------------------------------
# Wave 3 — doctor
# ---------------------------------------------------------------------------


def test_cmd_doctor_flags_missing_compose_fix(tmp_path, capsys) -> None:
    """Compose without disable-mcp triggers Bug 1 problem."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n  penpot-frontend:\n    image: penpotapp/frontend:latest\n",
        encoding="utf-8",
    )
    config = {
        "penpot_dir": str(tmp_path),
        "penpot_port": 9001,
        "mcp_port": 4401,
        "plugin_port": 4400,
    }
    with (
        patch("cataforge.integrations.penpot.has_command", return_value=True),
        patch(
            "cataforge.integrations.penpot.get_command_version",
            return_value="v22.11.0",
        ),
        patch("cataforge.integrations.penpot._is_penpot_running", return_value=False),
        patch("cataforge.integrations.penpot._is_mcp_running", return_value=False),
        patch("cataforge.integrations.penpot.is_port_listening", return_value=False),
        patch("os.path.isfile", side_effect=lambda p: p == str(compose)),
    ):
        rc = penpot.cmd_doctor(config)
    out = capsys.readouterr().out
    assert rc == 1
    assert "disable-mcp" in out or "force-recreate" in out


def test_cmd_doctor_passes_on_fixed_compose(tmp_path, capsys) -> None:
    """Compose with the fix applied + healthy env should not report problems."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n  penpot-frontend:\n    environment:\n"
        "      - PENPOT_FLAGS=foo disable-mcp\n"
        "      - PENPOT_MCP_URI=http://127.0.0.1\n",
        encoding="utf-8",
    )
    config = {
        "penpot_dir": str(tmp_path),
        "penpot_port": 9001,
        "mcp_port": 4401,
        "plugin_port": 4400,
    }
    with (
        patch("cataforge.integrations.penpot.has_command", return_value=True),
        patch(
            "cataforge.integrations.penpot.get_command_version",
            return_value="v22.11.0",
        ),
        patch("cataforge.integrations.penpot._is_penpot_running", return_value=True),
        patch("cataforge.integrations.penpot._is_mcp_running", return_value=True),
        patch("cataforge.integrations.penpot.is_port_listening", return_value=True),
        # MCP log absent → "MCP 可能从未启动" info, not a problem
        patch("os.path.isfile", side_effect=lambda p: p == str(compose)),
    ):
        rc = penpot.cmd_doctor(config)
    out = capsys.readouterr().out
    assert rc == 0
    assert "未发现已知问题" in out


def test_doctor_argparse_subcommand_dispatches() -> None:
    # Post-D5: dispatch routes through penpot.HANDLERS — patch the entry
    # there rather than the module-level function reference.
    mock = MagicMock(return_value=0)
    with (
        patch("cataforge.integrations.penpot.load_dotenv"),
        patch.dict(penpot.HANDLERS, {"doctor": mock}),
    ):
        rc = penpot.main(["doctor"])
    assert rc == 0
    mock.assert_called_once()


def test_init_argparse_subcommand_dispatches() -> None:
    mock = MagicMock(return_value=0)
    with (
        patch("cataforge.integrations.penpot.load_dotenv"),
        patch.dict(penpot.HANDLERS, {"init": mock}),
    ):
        rc = penpot.main(["init"])
    assert rc == 0
    mock.assert_called_once()
