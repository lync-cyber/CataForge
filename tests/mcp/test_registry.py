"""MCP registry + lifecycle integration tests."""

from __future__ import annotations

import sys
import time
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
