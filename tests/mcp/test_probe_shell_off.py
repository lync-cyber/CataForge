"""Tests: _probe_command rejects string targets and runs list targets shell=False."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from cataforge.runtime.mcp.lifecycle import MCPLifecycleManager


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


class TestProbeCommandShellOff:
    def test_string_target_yields_unknown_status(self, project: Path) -> None:
        """A string health_check.target must be rejected with status='unknown'."""
        _write_spec(
            project,
            "str-target",
            command=sys.executable,
            args=["-c", "import sys; sys.exit(0)"],
            health_check={
                "type": "command",
                "target": "curl http://x; rm -rf /",
                "timeout_seconds": 5,
            },
        )
        mgr = MCPLifecycleManager(project)
        state = mgr.health("str-target")
        assert state is not None
        lhc = state.last_health_check or ""
        assert "unknown" in lhc
        assert "list of args" in lhc
        assert "curl http://x; rm -rf /" in lhc

    def test_list_target_runs_shell_false(self, project: Path) -> None:
        """A list health_check.target calls the wrapper with the exact argv.

        ``shell=False`` is now structurally guaranteed: lifecycle goes through
        ``cataforge.utils.run_subprocess.run``, which has no ``shell=``
        parameter at all. The assertion is therefore on the argv shape.
        """
        _write_spec(
            project,
            "list-target",
            command=sys.executable,
            args=["-c", "import sys; sys.exit(0)"],
            health_check={
                "type": "command",
                "target": [sys.executable, "-c", "import sys; sys.exit(0)"],
                "timeout_seconds": 5,
            },
        )
        mgr = MCPLifecycleManager(project)

        captured_calls: list[dict] = []

        from cataforge.utils import run_subprocess as _wrapper

        original_run = _wrapper.run

        def capturing_run(args, **kwargs):
            captured_calls.append({"args": args, "kwargs": kwargs})
            return original_run(args, **kwargs)

        with patch("cataforge.runtime.mcp.lifecycle.run_proc", side_effect=capturing_run):
            state = mgr.health("list-target")

        assert state is not None
        lhc = state.last_health_check or ""
        assert "healthy" in lhc
        assert "exit 0" in lhc

        assert captured_calls, "wrapper must have been called"
        call = captured_calls[0]
        assert call["args"] == [sys.executable, "-c", "import sys; sys.exit(0)"], (
            "argv must be passed exactly as given"
        )

    def test_list_target_exit_nonzero_is_unhealthy(self, project: Path) -> None:
        """A list target that exits non-zero yields status='unhealthy'."""
        _write_spec(
            project,
            "list-fail",
            command=sys.executable,
            args=["-c", "import sys; sys.exit(0)"],
            health_check={
                "type": "command",
                "target": [sys.executable, "-c", "import sys; sys.exit(3)"],
                "timeout_seconds": 5,
            },
        )
        mgr = MCPLifecycleManager(project)
        state = mgr.health("list-fail")
        assert state is not None
        lhc = state.last_health_check or ""
        assert "unhealthy" in lhc
        assert "exit 3" in lhc
