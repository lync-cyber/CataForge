"""Backup, restore, and manifest operations for the scaffold directory."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from cataforge import __version__ as _RUNTIME_VERSION  # noqa: N812
from cataforge.core.errors import ConfigError
from cataforge.core.io import read_json
from cataforge.utils.atomic_write import atomic_write_text

MANIFEST_REL = ".scaffold-manifest.json"
MANIFEST_VERSION = 1

BACKUPS_DIRNAME = ".backups"
_BACKUP_TS_FMT = "%Y%m%d-%H%M%S"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_manifest(dest: Path, files_map: dict[str, str]) -> None:
    """Write ``.scaffold-manifest.json`` under *dest*."""
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "package_version": _RUNTIME_VERSION,
        "files": dict(sorted(files_map.items())),
    }
    path = dest / MANIFEST_REL
    payload = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    atomic_write_text(path, payload)


def read_manifest(dest: Path) -> dict[str, str]:
    """Read ``<dest>/.scaffold-manifest.json`` and return ``{rel: sha256}``.

    Returns an empty dict if the manifest is missing or malformed — the
    caller must treat absence as "no prior record" rather than an error,
    because projects scaffolded before the manifest landed will not have
    one until their next ``setup``/``upgrade apply`` run.
    """
    path = dest / MANIFEST_REL
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except ConfigError:
        return {}
    files_map = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files_map, dict):
        return {}
    return {str(k): str(v) for k, v in files_map.items() if isinstance(v, str)}


def _is_user_modified(target: Path, new_bytes: bytes, manifest_hash: str | None) -> bool:
    """Whether *target* carries edits a forced overwrite would destroy.

    Mirrors :func:`classify_scaffold_files`'s ``user-modified``/``drift``
    verdicts: the on-disk bytes differ from the incoming scaffold *and* from
    the recorded manifest hash (a clean prior install matches the manifest, so
    it is a safe ``update``). Unreadable targets fall through to overwrite.
    """
    try:
        disk_hash = _sha256(target.read_bytes())
    except OSError:
        return False
    return disk_hash != _sha256(new_bytes) and disk_hash != manifest_hash


def _now_ts() -> str:
    return datetime.now(UTC).strftime(_BACKUP_TS_FMT)


def _backups_root(cataforge_dir: Path) -> Path:
    return cataforge_dir / BACKUPS_DIRNAME


def _iter_payload(cataforge_dir: Path) -> Iterator[Path]:
    """Yield every direct child of ``.cataforge/`` except the backups dir."""
    if not cataforge_dir.is_dir():
        return
    for item in cataforge_dir.iterdir():
        if item.name == BACKUPS_DIRNAME:
            continue
        yield item


def create_backup(cataforge_dir: Path, *, ts: str | None = None) -> Path | None:
    """Snapshot ``cataforge_dir`` into ``<cataforge_dir>/.backups/<ts>/``.

    Returns the backup path, or ``None`` when *cataforge_dir* is empty
    (nothing to preserve, so a backup would be pointless).
    """
    items = list(_iter_payload(cataforge_dir))
    if not items:
        return None

    backup_dir = _backups_root(cataforge_dir) / (ts or _now_ts())
    backup_dir.mkdir(parents=True, exist_ok=False)
    for item in items:
        dest_item = backup_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest_item)
        else:
            shutil.copy2(item, dest_item)
    return backup_dir


def list_backups(cataforge_dir: Path) -> list[Path]:
    """List available backup snapshot paths, newest first.

    The ordering is lexicographic on the timestamp directory name, which
    matches creation order because the format is ``YYYYMMDD-HHMMSS``.
    """
    root = _backups_root(cataforge_dir)
    if not root.is_dir():
        return []
    return sorted(
        (p for p in root.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )


def restore_backup(cataforge_dir: Path, backup_dir: Path) -> Path:
    """Replace ``cataforge_dir`` contents with *backup_dir*.

    Current state (minus ``.backups/``) is first stashed into a fresh
    ``.backups/pre-rollback-<ts>/`` snapshot so the rollback is itself
    reversible. Returns the stash path so the caller can echo it.
    """
    if not backup_dir.is_dir():
        raise FileNotFoundError(f"backup not found: {backup_dir}")

    stash_ts = f"pre-rollback-{_now_ts()}"
    stash = create_backup(cataforge_dir, ts=stash_ts)

    for item in list(_iter_payload(cataforge_dir)):
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    for item in backup_dir.iterdir():
        dest_item = cataforge_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest_item)
        else:
            shutil.copy2(item, dest_item)

    return stash if stash is not None else cataforge_dir
