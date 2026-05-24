"""MCP registry + lifecycle integration tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

from cataforge.mcp.lifecycle import MCPLifecycleManager
from cataforge.mcp.registry import MCPRegistry
from cataforge.schema.mcp_spec import MCPServerSpec


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
        assert reg.get_server("prog") is not None

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


class TestLifecycle:
    def test_start_unknown_server_raises(self, project: Path) -> None:
        mgr = MCPLifecycleManager(project)
        with pytest.raises(ValueError, match="Unknown MCP server"):
            mgr.start("no-such")

    def test_start_stop_persists_state(self, project: Path) -> None:
        # Long-running child: block on stdin so stop() actually has to kill it.
        _write_spec(
            project,
            "sleeper",
            command=sys.executable,
            args=["-c", "import sys; sys.stdin.read()"],
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
            args=["-c", "import sys; sys.stdin.read()"],
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
        from cataforge.mcp import lifecycle as lc

        _write_spec(
            project,
            "ghost",
            command=sys.executable,
            args=["-c", "import sys; sys.stdin.read()"],
        )
        state_dir = project / ".cataforge" / ".mcp-state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "ghost.json").write_text(
            '{"spec_id": "ghost", "status": "running", "pid": 999999}\n',
            encoding="utf-8",
        )

        # Force the alive-check to report False for the fake pid.
        monkeypatch.setattr(lc, "_pid_alive", lambda pid: pid != 999999)

        mgr = MCPLifecycleManager(project)
        state = mgr.start("ghost")
        try:
            assert state.status == "running"
            assert state.pid is not None and state.pid != 999999
        finally:
            mgr.stop("ghost")

    def test_stop_waits_for_pid_to_die(self, project: Path) -> None:
        """stop() must not return until the pid is actually gone."""
        from cataforge.mcp import lifecycle as lc

        _write_spec(
            project,
            "waitable",
            command=sys.executable,
            args=["-c", "import sys; sys.stdin.read()"],
        )
        mgr = MCPLifecycleManager(project)
        state = mgr.start("waitable")
        pid = state.pid
        assert pid is not None and lc._pid_alive(pid)

        result = mgr.stop("waitable")
        assert result.status == "stopped"
        assert not lc._pid_alive(pid), (
            "stop() returned 'stopped' but the pid is still alive"
        )


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
        assert reg2.get_server("external") is not None

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

    def test_register_from_file_force_overwrites(
        self, project: Path, tmp_path: Path
    ) -> None:
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
        assert loaded is not None and loaded.name == "replaced"

    def test_register_from_canonical_path_is_noop_copy(self, project: Path) -> None:
        """Registering the spec already at .cataforge/mcp/<id>.yaml must not
        raise FileExistsError — it is the source and target both."""
        spec_path = _write_spec(project, "inplace")
        reg = MCPRegistry(project)
        reg.register_from_file(spec_path)
        assert reg.get_server("inplace") is not None
