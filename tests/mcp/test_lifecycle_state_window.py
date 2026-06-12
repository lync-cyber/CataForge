"""State-file read/attach semantics for MCPLifecycleManager.start()."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from cataforge.core.errors import ConfigError
from cataforge.core.schema.mcp_spec import MCPServerState
from cataforge.runtime.mcp import state_store
from cataforge.runtime.mcp.lifecycle import MCPLifecycleManager
from cataforge.runtime.mcp.state_store import load_state, save_state


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    return tmp_path


def _write_sleeper_spec(project: Path, spec_id: str) -> None:
    mcp_dir = project / ".cataforge" / "mcp"
    mcp_dir.mkdir(exist_ok=True)
    data = {
        "id": spec_id,
        "name": spec_id,
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-c", "import time; time.sleep(60)"],
    }
    (mcp_dir / f"{spec_id}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def _state_dir(project: Path) -> Path:
    return project / ".cataforge" / ".mcp-state"


def _transient_then_real(monkeypatch: pytest.MonkeyPatch, failures: int) -> list[int]:
    """Patch state_store.read_json to fail `failures` times with an OSError-caused
    ConfigError (the os.replace sharing-violation window), then delegate."""
    real = state_store.read_json
    calls: list[int] = []

    def fake(path: Any) -> Any:
        calls.append(1)
        if len(calls) <= failures:
            raise ConfigError(f"Cannot read JSON file {path}: boom") from OSError("sharing")
        return real(path)

    monkeypatch.setattr(state_store, "read_json", fake)
    return calls


class TestLoadStateRetry:
    def test_retries_transient_read_error(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_dir = _state_dir(project)
        save_state(state_dir, MCPServerState(spec_id="s1", status="running", pid=os.getpid()))
        _transient_then_real(monkeypatch, failures=2)

        loaded = load_state(state_dir, "s1")

        assert loaded is not None
        assert loaded.status == "running"
        assert loaded.pid == os.getpid()

    def test_heals_malformed_json_as_absent(self, project: Path) -> None:
        state_dir = _state_dir(project)
        state_dir.mkdir(parents=True)
        (state_dir / "s2.json").write_text("{not json", encoding="utf-8")

        assert load_state(state_dir, "s2") is None

    def test_raises_after_persistent_read_errors(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state_dir = _state_dir(project)
        save_state(state_dir, MCPServerState(spec_id="s3", status="running", pid=os.getpid()))
        monkeypatch.setattr(state_store, "_LOAD_RETRY_ATTEMPTS", 3)
        monkeypatch.setattr(state_store, "_LOAD_RETRY_INTERVAL_SECONDS", 0.0)
        _transient_then_real(monkeypatch, failures=99)

        with pytest.raises(ConfigError):
            load_state(state_dir, "s3")


class TestStartAttach:
    def _forbid_spawn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import cataforge.runtime.mcp.lifecycle as lifecycle_mod

        def boom(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("start() must attach, not spawn")

        monkeypatch.setattr(lifecycle_mod.subprocess, "Popen", boom)

    def test_attach_survives_replace_window_on_state_read(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_sleeper_spec(project, "attach")
        save_state(
            _state_dir(project),
            MCPServerState(spec_id="attach", status="running", pid=os.getpid()),
        )
        self._forbid_spawn(monkeypatch)
        _transient_then_real(monkeypatch, failures=1)

        result = MCPLifecycleManager(project).start("attach")

        assert result.pid == os.getpid()

    def test_attaches_to_live_unhealthy_server(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_sleeper_spec(project, "sick")
        save_state(
            _state_dir(project),
            MCPServerState(spec_id="sick", status="unhealthy", pid=os.getpid()),
        )
        self._forbid_spawn(monkeypatch)

        result = MCPLifecycleManager(project).start("sick")

        assert result.pid == os.getpid()
        assert result.status == "running"
