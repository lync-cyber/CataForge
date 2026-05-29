"""Concurrent-start tests for MCPLifecycleManager."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest
import yaml

from cataforge.core.schema.mcp_spec import MCPServerState
from cataforge.runtime.mcp.lifecycle import MCPLifecycleManager


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


class TestConcurrentStart:
    def test_concurrent_start_produces_single_pid(self, project: Path) -> None:
        """Two simultaneous start() calls on the same server must result in
        exactly one live process — no duplicate spawns."""
        _write_sleeper_spec(project, "concurrent")

        results: list[MCPServerState] = []
        exceptions: list[Exception] = []

        def do_start() -> MCPServerState:
            mgr = MCPLifecycleManager(project)
            return mgr.start("concurrent")

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(do_start) for _ in range(2)]
            for f in as_completed(futures):
                exc = f.exception()
                if exc is not None:
                    exceptions.append(exc)
                else:
                    results.append(f.result())

        assert not exceptions, f"unexpected exceptions during concurrent start: {exceptions}"

        running = [r for r in results if r.status == "running"]
        assert running, "at least one start() must return status='running'"

        # All running results must agree on the same PID — no duplicates.
        pids = {r.pid for r in running if r.pid is not None}
        assert len(pids) == 1, (
            f"concurrent start() spawned multiple distinct PIDs: {pids}"
        )

        # Clean up
        mgr = MCPLifecycleManager(project)
        mgr.stop("concurrent")

    def test_concurrent_start_state_file_consistent(self, project: Path) -> None:
        """After two concurrent start() calls the state file must be valid
        JSON and reflect a single consistent status."""
        _write_sleeper_spec(project, "statefile")

        def do_start() -> None:
            MCPLifecycleManager(project).start("statefile")

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(do_start), pool.submit(do_start)]
            for f in as_completed(futures):
                f.result()

        state_file = project / ".cataforge" / ".mcp-state" / "statefile.json"
        assert state_file.is_file(), "state file must exist after concurrent starts"

        import json
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert "status" in data, "state file must contain a 'status' key"
        assert data["status"] in ("running", "stopped", "error"), (
            f"unexpected status {data['status']!r} in state file"
        )

        # Clean up
        mgr = MCPLifecycleManager(project)
        mgr.stop("statefile")

    def test_concurrent_start_no_unhandled_exception(self, project: Path) -> None:
        """Neither thread must raise an unhandled exception."""
        _write_sleeper_spec(project, "noexc")

        raised: list[Exception] = []

        def do_start() -> None:
            try:
                MCPLifecycleManager(project).start("noexc")
            except Exception as e:
                raised.append(e)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(do_start), pool.submit(do_start)]
            for f in as_completed(futures):
                f.result()

        assert not raised, f"concurrent start() raised unhandled exceptions: {raised}"

        # Clean up
        MCPLifecycleManager(project).stop("noexc")
