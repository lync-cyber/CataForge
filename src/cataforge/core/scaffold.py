"""Copy the bundled ``.cataforge/`` scaffold into a user project.

The scaffold lives under :mod:`cataforge._assets.cataforge_scaffold` and is
shipped inside the wheel so ``pip install cataforge`` / ``uv tool install
cataforge`` give users a one-shot ``cataforge setup`` that can bootstrap a
fresh project from scratch — no git clone required.

Access goes through :func:`importlib.resources.files` so it works whether the
package is installed from a wheel, editable install, or running from source.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

try:
    from importlib.resources.abc import Traversable
except ImportError:  # Python 3.10 — `importlib.resources.abc` landed in 3.11.
    from importlib.abc import Traversable

# ``_RUNTIME_VERSION`` is deliberately named — it reads as "the runtime
# package version" at every call site, not as a constant.
from cataforge import __version__ as _RUNTIME_VERSION  # noqa: N812

_PKG = "cataforge._assets"
_SCAFFOLD_SUBDIR = "cataforge_scaffold"

MANIFEST_REL = ".scaffold-manifest.json"
MANIFEST_VERSION = 1

# Backups of the scaffold directory live under ``<cataforge_dir>/.backups/<ts>/``.
# Using a nested dir (rather than a sibling like ``.cataforge.bak-<ts>``) keeps
# the project root clean and means ``.gitignore`` only needs one pattern to cover
# both state dirs and rollback snapshots.
BACKUPS_DIRNAME = ".backups"
_BACKUP_TS_FMT = "%Y%m%d-%H%M%S"


def _stamp_framework_version(raw_bytes: bytes) -> bytes:
    """Overwrite the bundled ``framework.json`` ``version`` with the runtime.

    The bundled scaffold ships with a placeholder ``version`` value that can
    drift from the installed package (e.g. scaffold says ``0.1.0`` while the
    wheel is at ``0.1.1``).  That drift causes ``cataforge upgrade check`` to
    report "differs" forever, even directly after ``upgrade apply``.
    Stamping the runtime package version onto every write makes the package
    the single source of truth for the scaffold ``version`` field.
    """
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw_bytes
    if not isinstance(data, dict):
        return raw_bytes
    data["version"] = _RUNTIME_VERSION
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _scaffold_root() -> Traversable:
    return files(_PKG).joinpath(_SCAFFOLD_SUBDIR)


def iter_scaffold_files() -> Iterator[tuple[str, Traversable]]:
    """Yield ``(relative_posix_path, traversable)`` for every bundled file."""

    def walk(node: Traversable, prefix: str) -> Iterator[tuple[str, Traversable]]:
        for child in node.iterdir():
            rel = f"{prefix}{child.name}"
            if child.is_dir():
                yield from walk(child, rel + "/")
            else:
                yield rel, child

    yield from walk(_scaffold_root(), "")


# ---- merge strategies for user-writable scaffold files ----
#
# ``--force-scaffold`` must refresh framework config without clobbering the
# parts users are expected to edit (runtime.platform picked at setup time,
# upgrade.state maintained across upgrades). Files listed here receive a
# custom merge instead of a blind overwrite.

MergeFn = Callable[[bytes, Path], bytes]


def _merge_framework_json(new_bytes: bytes, target: Path) -> bytes:
    """Overwrite scaffold-owned keys while preserving user-owned state."""
    try:
        existing = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return new_bytes

    merged: dict[str, Any] = json.loads(new_bytes.decode("utf-8"))

    # Runtime package version is injected by _stamp_framework_version already;
    # keep it so the refreshed scaffold matches the installed package.
    merged["version"] = _RUNTIME_VERSION

    # runtime.platform is chosen by the user at setup time.
    existing_runtime = existing.get("runtime") or {}
    if isinstance(existing_runtime, dict) and "platform" in existing_runtime:
        merged.setdefault("runtime", {})["platform"] = existing_runtime["platform"]

    # upgrade.state is local-only and tracks the last applied upgrade.
    existing_upgrade = existing.get("upgrade") or {}
    if isinstance(existing_upgrade, dict) and "state" in existing_upgrade:
        merged.setdefault("upgrade", {})["state"] = existing_upgrade["state"]

    return (json.dumps(merged, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _preserve_if_exists(new_bytes: bytes, target: Path) -> bytes:
    """Keep user edits untouched — return the current content."""
    return target.read_bytes()


_MERGE_HANDLERS: dict[str, MergeFn] = {
    "framework.json": _merge_framework_json,
    # PROJECT-STATE.md is the project's living runbook — never clobber.
    "PROJECT-STATE.md": _preserve_if_exists,
}


def copy_scaffold_to(
    dest: Path,
    *,
    force: bool = False,
    backup: bool = True,
) -> tuple[list[Path], list[Path], Path | None]:
    """Copy the bundled scaffold into *dest* (typically ``<project>/.cataforge``).

    Returns ``(written, skipped, backup_path)``. ``backup_path`` is the
    snapshot created before a forced refresh (or ``None`` when there was
    nothing to snapshot, or when *backup* was suppressed).

    When *force* is ``True`` existing files are overwritten, except for
    files registered in :data:`_MERGE_HANDLERS` which receive a field-level
    merge that preserves user-owned state (e.g.
    ``framework.json.runtime.platform``). Set *backup* to ``False`` to skip
    the automatic snapshot — callers doing a fresh install or their own
    backup should pass ``backup=False``.

    On every invocation, also writes ``<dest>/.scaffold-manifest.json``
    recording the bytes-hash of each written file and the package version
    that produced it, so later upgrades can classify per-file drift.
    """
    backup_path: Path | None = None
    if force and backup and dest.is_dir():
        backup_path = create_backup(dest)

    written: list[Path] = []
    skipped: list[Path] = []
    manifest_files: dict[str, str] = {}
    for rel, src in iter_scaffold_files():
        target = dest / rel
        exists = target.exists()

        if exists and not force:
            skipped.append(target)
            if target.is_file():
                with contextlib.suppress(OSError):
                    manifest_files[rel] = _sha256(target.read_bytes())
            continue

        with as_file(src) as src_path:
            new_bytes = Path(src_path).read_bytes()

        # Stamp the runtime package version onto framework.json for every
        # write (fresh copy or force-refresh) — keeps the scaffold version
        # aligned with the installed package without a template engine.
        if rel == "framework.json":
            new_bytes = _stamp_framework_version(new_bytes)

        if exists and force:
            handler = _MERGE_HANDLERS.get(rel)
            if handler is not None:
                new_bytes = handler(new_bytes, target)

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(new_bytes)
        manifest_files[rel] = _sha256(new_bytes)
        written.append(target)

    _write_manifest(dest, manifest_files)
    return written, skipped, backup_path


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
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    path.write_text(payload, encoding="utf-8")


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
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    files_map = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files_map, dict):
        return {}
    return {str(k): str(v) for k, v in files_map.items() if isinstance(v, str)}


def classify_scaffold_files(
    dest: Path,
) -> list[tuple[str, str]]:
    """Classify every bundled scaffold file against its *dest* counterpart.

    Returns ``(rel, status)`` tuples where ``status`` is one of:

    * ``new``                  — target does not exist on disk.
    * ``unchanged``            — target bytes already match the bundled scaffold.
    * ``update``               — target bytes match the recorded manifest hash
      (clean prior install) and differ from the bundled scaffold.
    * ``user-modified``        — target bytes differ from both manifest and
      bundled scaffold; ``--force-scaffold`` will overwrite the user edits.
    * ``preserved``            — file is in :data:`_MERGE_HANDLERS`; refresh
      performs a field-level merge instead of a blind overwrite.
    * ``drift``                — no manifest entry and target differs from
      bundled scaffold (legacy projects scaffolded pre-manifest).
    """
    manifest = read_manifest(dest)
    results: list[tuple[str, str]] = []
    for rel, src in iter_scaffold_files():
        target = dest / rel
        with as_file(src) as src_path:
            new_bytes = Path(src_path).read_bytes()
        if rel == "framework.json":
            new_bytes = _stamp_framework_version(new_bytes)
        new_hash = _sha256(new_bytes)

        if not target.exists():
            results.append((rel, "new"))
            continue

        if rel in _MERGE_HANDLERS:
            results.append((rel, "preserved"))
            continue

        try:
            disk_hash = _sha256(target.read_bytes())
        except OSError:
            results.append((rel, "user-modified"))
            continue

        if disk_hash == new_hash:
            results.append((rel, "unchanged"))
            continue

        manifest_hash = manifest.get(rel)
        if manifest_hash is None:
            results.append((rel, "drift"))
        elif disk_hash == manifest_hash:
            results.append((rel, "update"))
        else:
            results.append((rel, "user-modified"))
    return results


# ---- scaffold backup / rollback ---------------------------------------------
#
# A backup is a snapshot of the ``.cataforge/`` directory (minus ``.backups/``
# itself) taken just before a destructive refresh. Users can ``upgrade
# rollback`` to restore a snapshot without depending on git.


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime(_BACKUP_TS_FMT)


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
