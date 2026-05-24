"""MCP lifecycle — CATAFORGE_MCP_DEBUG=1 passes stderr=None to Popen."""

from __future__ import annotations

import contextlib
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cataforge.mcp.lifecycle import MCPLifecycleManager
from cataforge.schema.mcp_spec import MCPServerSpec


def _make_spec(server_id: str = "test-server") -> MCPServerSpec:
    return MCPServerSpec(
        id=server_id,
        command="echo",
        args=["hello"],
    )


@pytest.fixture()
def lifecycle(tmp_path: Path) -> MCPLifecycleManager:
    (tmp_path / ".cataforge").mkdir()
    return MCPLifecycleManager(project_root=tmp_path)


class TestMCPDebugStderr:
    def test_default_uses_devnull(
        self, lifecycle: MCPLifecycleManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CATAFORGE_MCP_DEBUG", raising=False)
        spec = _make_spec()
        captured: dict = {}

        def fake_popen(cmd, **kwargs):
            captured.update(kwargs)
            mock = MagicMock()
            mock.pid = 12345
            return mock

        lifecycle._registry.get_server = MagicMock(return_value=spec)  # type: ignore[method-assign]

        with (
            patch("subprocess.Popen", side_effect=fake_popen),
            patch.object(lifecycle, "health", return_value=None),
            contextlib.suppress(Exception),
        ):
            lifecycle.start(spec.id)

        assert captured.get("stderr") == subprocess.DEVNULL

    def test_debug_env_inherits_stderr(
        self, lifecycle: MCPLifecycleManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CATAFORGE_MCP_DEBUG", "1")
        spec = _make_spec()
        captured: dict = {}

        def fake_popen(cmd, **kwargs):
            captured.update(kwargs)
            mock = MagicMock()
            mock.pid = 12345
            return mock

        lifecycle._registry.get_server = MagicMock(return_value=spec)  # type: ignore[method-assign]

        with (
            patch("subprocess.Popen", side_effect=fake_popen),
            patch.object(lifecycle, "health", return_value=None),
            contextlib.suppress(Exception),
        ):
            lifecycle.start(spec.id)

        assert captured.get("stderr") is None
