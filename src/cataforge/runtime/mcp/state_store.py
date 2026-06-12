"""MCP server state persistence — atomic JSON read/write/delete."""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from pathlib import Path

from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.core.schema.mcp_spec import MCPServerState

_LOAD_RETRY_ATTEMPTS = 10
_LOAD_RETRY_INTERVAL_SECONDS = 0.02


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
    """Load persisted state; ``None`` means *no state exists*.

    A reader can collide with the microsecond window of a concurrent
    ``os.replace`` in :func:`save_state` (Windows raises a sharing
    violation on the destination). The file still being present
    distinguishes that transient condition from a genuinely absent
    state, so retry instead of reporting ``None`` — a false ``None``
    here makes ``MCPLifecycleManager.start()`` spawn a duplicate
    server. Malformed JSON is not retried (it cannot self-repair) and
    heals as "no state"; a read error that persists past the retry
    budget is raised so callers see the I/O problem instead of acting
    on a wrong answer.
    """
    path = state_dir / f"{server_id}.json"
    last_error: ConfigError | None = None
    for _ in range(_LOAD_RETRY_ATTEMPTS):
        if not path.is_file():
            return None
        try:
            data = read_json(path)
        except ConfigError as e:
            if not isinstance(e.__cause__, OSError):
                return None
            last_error = e
            time.sleep(_LOAD_RETRY_INTERVAL_SECONDS)
            continue
        return MCPServerState.model_validate(data)
    raise last_error if last_error is not None else ConfigError(f"Cannot read {path}")
