"""MCP registry + lifecycle integration tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

from cataforge.core.schema.mcp_spec import MCPServerSpec
from cataforge.runtime.mcp.lifecycle import MCPLifecycleManager
from cataforge.runtime.mcp.registry import MCPRegistry


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    return tmp_path


def _write_spec(project: Path, spec_id: str, **overrides) -> Path:
    mcp_dir = project / ".cataforge" / "mcp"
    mcp_dir.mkdir(exist_ok=True)
    data = {
        "id": spec_id,
        "name": spec_id,
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-c", "import sys; sys.exit(0)"],
    }
    data.update(overrides)
    path = mcp_dir / f"{spec_id}.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


class TestRegistryDiscovery:
    def test_declarative_yaml_discovered(self, project: Path) -> None:
        _write_spec(project, "my-server")
        reg = MCPRegistry(project)
        ids = [s.id for s in reg.list_servers()]
        assert "my-server" in ids

    def test_invalid_yaml_is_skipped(self, project: Path) -> None:
        mcp_dir = project / ".cataforge" / "mcp"
        mcp_dir.mkdir()
        (mcp_dir / "bad.yaml").write_text("not a mapping\n", encoding="utf-8")
        _write_spec(project, "good")
        reg = MCPRegistry(project)
        ids = [s.id for s in reg.list_servers()]
        assert "good" in ids

    def test_programmatic_registration(self, project: Path) -> None:
        reg = MCPRegistry(project)
        reg.register(MCPServerSpec(id="prog", command="echo"))
        assert reg.get_server("prog").id == "prog"

    def test_get_missing_server_returns_none(self, project: Path) -> None:
        reg = MCPRegistry(project)
        assert reg.get_server("nope") is None

    def test_platform_config_merges_overrides(self, project: Path) -> None:
        _write_spec(
            project,
            "srv",
            platform_config={"cursor": {"args": ["--cursor-mode"]}},
        )
        reg = MCPRegistry(project)
        cfg = reg.get_platform_config("srv", "cursor")
        assert cfg["args"] == ["--cursor-mode"]
        # Un-overridden platform falls back to base.
        base = reg.get_platform_config("srv", "claude-code")
        assert "command" in base

    def test_platform_config_unknown_server(self, project: Path) -> None:
        reg = MCPRegistry(project)
        assert reg.get_platform_config("nope", "cursor") == {}

    def test_http_url_yields_neutral_payload(self, project: Path) -> None:
        # A remote spec resolves to a neutral {transport, url} payload for every
        # platform — no command/args, no per-platform key spelling.
        _write_spec(
            project,
            "remote-srv",
            transport="http",
            command="",
            args=[],
            url="http://localhost:9001/mcp",
        )
        reg = MCPRegistry(project)
        for plat in ("claude-code", "cursor", "codex", "opencode"):
            cfg = reg.get_platform_config("remote-srv", plat)
            assert cfg == {"transport": "http", "url": "http://localhost:9001/mcp"}
            assert "command" not in cfg and "args" not in cfg

    def test_url_alone_defaults_transport_http(self, project: Path) -> None:
        # A url with no explicit remote transport still marks the server remote.
        _write_spec(project, "url-srv", command="", url="http://localhost:9001/mcp/stream")
        reg = MCPRegistry(project)
        cfg = reg.get_platform_config("url-srv", "cursor")
        assert cfg == {"transport": "http", "url": "http://localhost:9001/mcp/stream"}

    def test_non_ascii_spec_parsed_utf8(self, project: Path) -> None:
        # A spec with non-ASCII text must parse regardless of platform locale.
        _write_spec(project, "zh-srv", description="设计工具 MCP")
        reg = MCPRegistry(project)
        assert reg.get_server("zh-srv") is not None


class TestLifecycle:
    def test_start_unknown_server_raises(self, project: Path) -> None:
        mgr = MCPLifecycleManager(project)
        with pytest.raises(ValueError, match="Unknown MCP server"):
            mgr.start("no-such")

    def test_start_stop_persists_state(self, project: Path) -> None:
        # Long-running child: ``time.sleep(60)`` keeps the process alive
        # independent of stdin state (CI runners close stdin, which would
        # let a ``sys.stdin.read()``-blocker exit immediately and confuse
        # the stop() flow with a zombie). SIGTERM still interrupts sleep,
        # so stop() exercises the SIGTERM → wait path as designed.
        _write_spec(
            project,
            "sleeper",
            command=sys.executable,
            args=["-c", "import time; time.sleep(60)"],
        )
        mgr = MCPLifecycleManager(project)
        state = mgr.start("sleeper")
        assert state.status == "running"
        assert state.pid is not None

        state_file = project / ".cataforge" / ".mcp-state" / "sleeper.json"
        assert state_file.is_file()

        stopped = mgr.stop("sleeper")
        assert stopped.status == "stopped"

    def test_stop_without_prior_start(self, project: Path) -> None:
        _write_spec(project, "never-started")
        mgr = MCPLifecycleManager(project)
        state = mgr.stop("never-started")
        assert state.status == "stopped"

    def test_start_bad_command_records_error(self, project: Path) -> None:
        _write_spec(
            project,
            "broken",
            command="/definitely/not/a/real/binary-xyz-123",
            args=[],
        )
        mgr = MCPLifecycleManager(project)
        state = mgr.start("broken")
        assert state.status == "error"
        assert state.error_message

    def test_start_idempotent_when_already_running(self, project: Path) -> None:
        """A fresh CLI process sees the persisted 'running' state and
        returns it instead of spawning a second child."""
        _write_spec(
            project,
            "twice",
            command=sys.executable,
            args=["-c", "import time; time.sleep(60)"],
        )
        mgr1 = MCPLifecycleManager(project)
        first = mgr1.start("twice")
        try:
            assert first.status == "running" and first.pid is not None

            # Simulate a new CLI invocation: fresh registry + lifecycle
            # objects, but the on-disk state and the live child remain.
            mgr2 = MCPLifecycleManager(project)
            second = mgr2.start("twice")
            assert second.status == "running"
            assert second.pid == first.pid, (
                "start() must return the existing pid, not spawn a duplicate"
            )
        finally:
            mgr1.stop("twice")

    def test_start_cleans_stale_running_state(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If a persisted 'running' state references a dead pid, start()
        clears it and spawns a fresh process instead of refusing."""
        from cataforge.runtime.mcp import lifecycle as lc

        _write_spec(
            project,
            "ghost",
            command=sys.executable,
            args=["-c", "import time; time.sleep(60)"],
        )
        state_dir = project / ".cataforge" / ".mcp-state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "ghost.json").write_text(
            '{"spec_id": "ghost", "status": "running", "pid": 999999}\n',
            encoding="utf-8",
        )

        # Force the alive-check to report False for the fake pid, but keep
        # real behaviour for every other pid — otherwise the live child we
        # spawn below would read as alive forever, and teardown's stop()
        # would burn the full SIGTERM + SIGKILL timeouts waiting for a pid
        # that is already gone.
        real_pid_alive = lc.pid_alive
        monkeypatch.setattr(
            lc,
            "pid_alive",
            lambda pid: False if pid == 999999 else real_pid_alive(pid),
        )

        mgr = MCPLifecycleManager(project)
        state = mgr.start("ghost")
        try:
            assert state.status == "running"
            assert state.pid is not None and state.pid != 999999
        finally:
            mgr.stop("ghost")

    def test_stop_waits_for_pid_to_die(self, project: Path) -> None:
        """stop() must not return until the pid is actually gone."""
        from cataforge.runtime.mcp import lifecycle as lc

        _write_spec(
            project,
            "waitable",
            command=sys.executable,
            args=["-c", "import time; time.sleep(60)"],
        )
        mgr = MCPLifecycleManager(project)
        state = mgr.start("waitable")
        pid = state.pid
        assert pid is not None and lc.pid_alive(pid)

        result = mgr.stop("waitable")
        assert result.status == "stopped"
        assert not lc.pid_alive(pid), "stop() returned 'stopped' but the pid is still alive"


class TestRegistryPersistence:
    def test_register_from_file_copies_to_canonical_path(
        self, project: Path, tmp_path: Path
    ) -> None:
        """A spec registered from outside .cataforge/mcp/ must be copied
        in so a fresh process can discover it."""
        external = tmp_path / "external"
        external.mkdir()
        spec_path = external / "external.yaml"
        spec_path.write_text(
            yaml.safe_dump(
                {
                    "id": "external",
                    "name": "external",
                    "transport": "stdio",
                    "command": "echo",
                }
            ),
            encoding="utf-8",
        )

        reg1 = MCPRegistry(project)
        reg1.register_from_file(spec_path)

        canonical = project / ".cataforge" / "mcp" / "external.yaml"
        assert canonical.is_file(), "spec must be persisted to .cataforge/mcp/"

        # Fresh registry (simulates new process) discovers it.
        reg2 = MCPRegistry(project)
        assert reg2.get_server("external").id == "external"

    def test_register_from_file_refuses_overwrite_by_default(
        self, project: Path, tmp_path: Path
    ) -> None:
        _write_spec(project, "existing")
        replacement = tmp_path / "replacement.yaml"
        replacement.write_text(
            yaml.safe_dump(
                {
                    "id": "existing",
                    "name": "different",
                    "transport": "stdio",
                    "command": "echo",
                }
            ),
            encoding="utf-8",
        )

        reg = MCPRegistry(project)
        with pytest.raises(FileExistsError, match="already registered"):
            reg.register_from_file(replacement)

    def test_register_from_file_force_overwrites(self, project: Path, tmp_path: Path) -> None:
        _write_spec(project, "existing", name="original")
        replacement = tmp_path / "replacement.yaml"
        replacement.write_text(
            yaml.safe_dump(
                {
                    "id": "existing",
                    "name": "replaced",
                    "transport": "stdio",
                    "command": "echo",
                }
            ),
            encoding="utf-8",
        )

        reg = MCPRegistry(project)
        spec = reg.register_from_file(replacement, overwrite=True)
        assert spec.name == "replaced"

        reg2 = MCPRegistry(project)
        loaded = reg2.get_server("existing")
        assert loaded.name == "replaced"

    def test_register_from_canonical_path_is_noop_copy(self, project: Path) -> None:
        """Registering the spec already at .cataforge/mcp/<id>.yaml must not
        raise FileExistsError — it is the source and target both."""
        spec_path = _write_spec(project, "inplace")
        reg = MCPRegistry(project)
        reg.register_from_file(spec_path)
        assert reg.get_server("inplace").id == "inplace"


class TestHealth:
    def test_health_unknown_server_returns_none(self, project: Path) -> None:
        mgr = MCPLifecycleManager(project)
        assert mgr.health("ghost") is None

    def test_health_without_spec_falls_back_to_pid_alive(self, project: Path) -> None:
        """A spec without ``health_check`` makes ``health()`` probe pid alive
        and write the result to ``last_health_check``."""
        _write_spec(
            project,
            "no-check",
            command=sys.executable,
            args=["-c", "import time; time.sleep(60)"],
        )
        mgr = MCPLifecycleManager(project)
        mgr.start("no-check")
        try:
            state = mgr.health("no-check")
            assert state.status == "running"
            assert "healthy" in state.last_health_check
            assert "pid_alive=True" in state.last_health_check
        finally:
            mgr.stop("no-check")

    def test_health_tcp_probe_against_listening_socket(self, project: Path) -> None:
        """An open TCP port reports healthy; closed reports unhealthy."""
        import socket as _socket

        listener = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        try:
            _write_spec(
                project,
                "tcp-srv",
                command="echo",
                args=["registered-but-not-run"],
                health_check={
                    "type": "tcp",
                    "target": f"127.0.0.1:{port}",
                    "timeout_seconds": 2,
                },
            )
            mgr = MCPLifecycleManager(project)
            healthy = mgr.health("tcp-srv")
            assert "healthy" in (healthy.last_health_check or "")
            assert "connected" in (healthy.last_health_check or "")
        finally:
            listener.close()

        # Same spec, now nothing listening on that port.
        unhealthy = mgr.health("tcp-srv")
        assert "unhealthy" in (unhealthy.last_health_check or "")

    def test_health_command_probe_uses_exit_code(self, project: Path) -> None:
        _write_spec(
            project,
            "cmd-ok",
            command="echo",
            args=["registered"],
            health_check={
                "type": "command",
                "target": [sys.executable, "-c", "import sys; sys.exit(0)"],
                "timeout_seconds": 5,
            },
        )
        _write_spec(
            project,
            "cmd-bad",
            command="echo",
            args=["registered"],
            health_check={
                "type": "command",
                "target": [sys.executable, "-c", "import sys; sys.exit(7)"],
                "timeout_seconds": 5,
            },
        )
        mgr = MCPLifecycleManager(project)

        ok = mgr.health("cmd-ok")
        assert "healthy" in (ok.last_health_check or "")
        assert "exit 0" in (ok.last_health_check or "")

        bad = mgr.health("cmd-bad")
        assert "unhealthy" in (bad.last_health_check or "")
        assert "exit 7" in (bad.last_health_check or "")
