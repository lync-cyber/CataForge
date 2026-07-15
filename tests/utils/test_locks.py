"""Cross-process file lock: exclusivity, TTL steal, owner-info rejection."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

from cataforge.utils import locks
from cataforge.utils.locks import LockHeldError, file_lock


class TestFileLock:
    def test_exclusive_within_process(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "locks" / "test.lock"
        acquired: list[str] = []

        def worker(name: str) -> None:
            with file_lock(lock_path, timeout=5.0, owner=name):
                acquired.append(f"{name}:in")
                time.sleep(0.05)
                acquired.append(f"{name}:out")

        threads = [threading.Thread(target=worker, args=(f"t{i}",)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Critical sections never interleave: every :in is immediately followed
        # by the same worker's :out.
        for i in range(0, len(acquired), 2):
            assert acquired[i].split(":")[0] == acquired[i + 1].split(":")[0]

    def test_reject_when_held(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "test.lock"
        with (
            file_lock(lock_path, owner="first"),
            pytest.raises(LockHeldError) as exc_info,
            file_lock(lock_path, timeout=0, owner="second"),
        ):
            pass
        assert "first" in str(exc_info.value)

    def test_released_on_exit(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "test.lock"
        with file_lock(lock_path, owner="a"):
            pass
        assert not lock_path.exists()
        with file_lock(lock_path, timeout=0, owner="b"):
            pass

    def test_released_on_exception(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "test.lock"
        with pytest.raises(RuntimeError), file_lock(lock_path, owner="a"):
            raise RuntimeError("boom")
        assert not lock_path.exists()

    def test_stale_lock_stolen_after_ttl(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "test.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        stale = {"owner": "dead-process", "pid": 999999, "created_at": time.time() - 3600}
        lock_path.write_text(json.dumps(stale), encoding="utf-8")
        with file_lock(lock_path, timeout=0, ttl_seconds=600, owner="new"):
            payload = json.loads(lock_path.read_text("utf-8"))
            assert payload["owner"] == "new"

    def test_fresh_lock_not_stolen(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "test.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fresh = {"owner": "alive", "pid": 1, "created_at": time.time()}
        lock_path.write_text(json.dumps(fresh), encoding="utf-8")
        with (
            pytest.raises(LockHeldError),
            file_lock(lock_path, timeout=0, ttl_seconds=600, owner="new"),
        ):
            pass

    def test_corrupt_lock_treated_as_stale(self, tmp_path: Path) -> None:
        # unreadable payload alone is not proof of abandonment — the file's
        # own age is; corrupt AND past TTL → reclaimable
        lock_path = tmp_path / "test.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("not-json", encoding="utf-8")
        old = time.time() - 3600
        os.utime(lock_path, (old, old))
        with file_lock(lock_path, timeout=0, ttl_seconds=600, owner="new"):
            pass

    def test_mid_write_lock_not_reclaimed(self, tmp_path: Path) -> None:
        # the O_EXCL-created lock file exists but its holder payload is not
        # yet written (the acquire window): an empty fresh file is a live
        # lock, not a corrupt-and-stealable one
        lock_path = tmp_path / "test.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.touch()
        with (
            pytest.raises(LockHeldError),
            file_lock(lock_path, timeout=0, ttl_seconds=600, owner="thief"),
        ):
            pass
        assert lock_path.exists()  # the mid-acquisition lock survived the probe

    def test_steal_verifies_holder_before_unlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # between the staleness snapshot and the unlink, the lock may be
        # released and re-acquired by a live owner — the steal must re-verify
        # the holder and back off instead of deleting the new owner's lock
        lock_path = tmp_path / "test.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fresh = {"owner": "alive", "pid": 1, "created_at": time.time()}
        lock_path.write_text(json.dumps(fresh), encoding="utf-8")

        stale = {"owner": "dead", "pid": 2, "created_at": time.time() - 3600}
        snapshots: list[dict[str, object]] = [stale]  # first probe sees the old holder
        real_read = locks._read_holder

        def racy_read(path: Path) -> dict[str, object]:
            return snapshots.pop(0) if snapshots else real_read(path)

        monkeypatch.setattr(locks, "_read_holder", racy_read)
        with (
            pytest.raises(LockHeldError),
            file_lock(lock_path, timeout=0, ttl_seconds=600, owner="thief"),
        ):
            pass
        assert json.loads(lock_path.read_text("utf-8"))["owner"] == "alive"
