"""MCP server lifecycle management — start, stop, health check."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from cataforge.core.paths import ProjectPaths, find_project_root
from cataforge.mcp.registry import MCPRegistry
from cataforge.schema.mcp_spec import MCPServerSpec, MCPServerState


class MCPLifecycleManager:
    """Manage MCP server processes."""

    def __init__(
        self,
        project_root: Path | None = None,
        registry: MCPRegistry | None = None,
    ) -> None:
        self._paths = ProjectPaths(project_root or find_project_root())
        self._registry = registry or MCPRegistry(self._paths.root)
        self._state_dir = self._paths.mcp_state_dir

    def start(self, server_id: str) -> MCPServerState:
        """Start an MCP server."""
        spec = self._registry.get_server(server_id)
        if spec is None:
            raise ValueError(f"Unknown MCP server: {server_id}")

        state = self._registry.get_state(server_id)
        if state and state.status == "running":
            return state

        self._state_dir.mkdir(parents=True, exist_ok=True)

        try:
            cmd = [spec.command] + spec.args
            env = self._build_env(spec)

            proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(self._paths.root),
            )

            new_state = MCPServerState(
                spec_id=server_id,
                status="running",
                pid=proc.pid,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            self._save_state(new_state)
            return new_state

        except Exception as e:
            error_state = MCPServerState(
                spec_id=server_id,
                status="error",
                error_message=str(e),
            )
            self._save_state(error_state)
            return error_state

    def stop(self, server_id: str) -> MCPServerState:
        """Stop an MCP server."""
        state = self._load_state(server_id)
        if state is None or state.pid is None:
            return MCPServerState(spec_id=server_id, status="stopped")

        with contextlib.suppress(ProcessLookupError, OSError):
            os.kill(state.pid, signal.SIGTERM)

        new_state = MCPServerState(spec_id=server_id, status="stopped")
        self._save_state(new_state)
        return new_state

    def _build_env(self, spec: MCPServerSpec) -> dict[str, str]:
        env = os.environ.copy()
        for k, v in spec.env.items():
            if v.startswith("${") and v.endswith("}"):
                env_key = v[2:-1]
                env[k] = os.environ.get(env_key, "")
            else:
                env[k] = v
        return env

    def _save_state(self, state: MCPServerState) -> None:
        path = self._state_dir / f"{state.spec_id}.json"
        path.write_text(
            json.dumps(
                {
                    "spec_id": state.spec_id,
                    "status": state.status,
                    "pid": state.pid,
                    "port": state.port,
                    "started_at": state.started_at,
                    "error_message": state.error_message,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _load_state(self, server_id: str) -> MCPServerState | None:
        path = self._state_dir / f"{server_id}.json"
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return MCPServerState.model_validate(data)
