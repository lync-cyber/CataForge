"""MCP server state persistence — atomic JSON read/write/delete."""

from __future__ import annotations

import contextlib
import json
import os
import threading
from pathlib import Path

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.core.schema.mcp_spec import MCPServerState


def save_state(state_dir: Path, state: MCPServerState) -> None:
    """Write *state* atomically: dump to a sibling tmpfile, then rename.

    The rename is atomic on POSIX and on NTFS (replacement semantics), so
    any reader sees either the previous content or the fully-written new
    content, never a partial buffer.
    """
    path = state_dir / f"{state.spec_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            {
                "spec_id": state.spec_id,
                "status": state.status,
                "pid": state.pid,
                "port": state.port,
                "started_at": state.started_at,
                "last_health_check": state.last_health_check,
                "error_message": state.error_message,
            },
            indent=2,
        )
        + "\n"
    )
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{threading.get_ident()}")
    tmp.write_text(payload)
    os.replace(str(tmp), str(path))


def delete_state(state_dir: Path, server_id: str) -> None:
    path = state_dir / f"{server_id}.json"
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def load_state(state_dir: Path, server_id: str) -> MCPServerState | None:
    path = state_dir / f"{server_id}.json"
    if not path.is_file():
        return None
    try:
        data = read_json(path)
    except ConfigError:
        return None
    return MCPServerState.model_validate(data)
