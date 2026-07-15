"""Cross-process advisory file lock (O_CREAT|O_EXCL + TTL steal).

Guards read-modify-write sequences on shared project files
(``framework.json``, deploy state). ``os.open`` with ``O_EXCL`` is atomic
on both POSIX and Windows; stale locks (owner crashed) are reclaimed once
their TTL expires, so no lock ever needs manual cleanup.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import time
from collections.abc import Iterator
from pathlib import Path

__all__ = ["LockHeldError", "file_lock"]


class LockHeldError(RuntimeError):
    """The lock is held by another live owner and ``timeout`` elapsed."""

    def __init__(self, lock_path: Path, holder: dict[str, object]) -> None:
        self.lock_path = lock_path
        self.holder = holder
        owner = holder.get("owner", "?")
        pid = holder.get("pid", "?")
        super().__init__(
            f"lock {lock_path} is held by {owner!r} (pid {pid}); "
            "another CataForge write operation is in progress"
        )


def _read_holder(lock_path: Path) -> dict[str, object]:
    try:
        data = json.loads(lock_path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _is_stale(holder: dict[str, object], ttl_seconds: float, mtime: float) -> bool:
    created = holder.get("created_at")
    if not isinstance(created, int | float):
        # corrupt or mid-write payload: the file's own age decides — a lock
        # caught between O_EXCL create and payload write is alive, not stealable
        created = mtime
    return (time.time() - created) > ttl_seconds


def _steal(lock_path: Path, snapshot: dict[str, object]) -> None:
    """Reclaim a stale lock, but only while it still matches *snapshot* — it
    may have been released and re-acquired by a live owner in the meantime."""
    if _read_holder(lock_path) == snapshot:
        with contextlib.suppress(OSError):
            lock_path.unlink()


def _try_acquire(lock_path: Path, payload: str) -> bool:
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    return True


@contextlib.contextmanager
def file_lock(
    lock_path: Path,
    *,
    timeout: float = 10.0,
    ttl_seconds: float = 600.0,
    poll_interval: float = 0.05,
    owner: str | None = None,
) -> Iterator[None]:
    """Hold *lock_path* exclusively for the duration of the ``with`` block.

    ``timeout=0`` rejects immediately when the lock is held (fail-fast mode
    for user-facing commands); a positive timeout polls until acquired or
    raises :class:`LockHeldError` with the holder's identity.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "owner": owner or f"pid-{os.getpid()}",
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "created_at": time.time(),
        }
    )

    deadline = time.monotonic() + timeout
    while True:
        if _try_acquire(lock_path, payload):
            break
        try:
            mtime = lock_path.stat().st_mtime
        except OSError:
            continue  # lock vanished between attempts — retry the acquire
        holder = _read_holder(lock_path)
        if _is_stale(holder, ttl_seconds, mtime):
            _steal(lock_path, holder)
            continue
        if time.monotonic() >= deadline:
            raise LockHeldError(lock_path, holder)
        time.sleep(poll_interval)

    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            lock_path.unlink()
