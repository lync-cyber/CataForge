"""Store snapshot: serialize all quads to NQuads file; restore from file."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from cataforge.kg._config import KGConfig
from cataforge.kg._errors import KGError, KGStoreAlreadyExistsError
from cataforge.kg.store import init_store

if TYPE_CHECKING:
    import pyoxigraph as ox


@dataclass
class SnapshotMeta:
    path: Path
    timestamp: str
    quad_count: int
    active_doc_types: list[str]
    store_backend: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path)
        return d


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sanitize_label(label: str | None) -> str:
    if not label:
        return ""
    return "_" + label.replace(" ", "-").replace("/", "-")


def create_snapshot(
    store: ox.Store,
    config: KGConfig,
    output_dir: Path,
    *,
    label: str | None = None,
) -> SnapshotMeta:
    """Serialize all quads in the store to an NQuads file + metadata sidecar."""
    import pyoxigraph as ox  # noqa: PLC0415

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = _utc_now_iso()
    suffix = _sanitize_label(label)
    nq_path = output_dir / f"{ts}{suffix}.nq"

    with nq_path.open("wb") as f:
        store.dump(f, ox.RdfFormat.N_QUADS)

    quad_count = sum(1 for _ in store.quads_for_pattern(None, None, None, None))

    meta = SnapshotMeta(
        path=nq_path,
        timestamp=ts,
        quad_count=quad_count,
        active_doc_types=sorted(config.kg_active_doc_types),
        store_backend=config.store_backend,
    )

    meta_path = nq_path.with_suffix(".meta.json")
    meta_path.write_text(
        json.dumps(meta.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return meta


def restore_snapshot(
    snapshot_path: Path,
    config: KGConfig,
    *,
    force: bool = False,
) -> int:
    """Restore a store from an NQuads snapshot file.

    Returns the number of quads loaded (excluding bootstrap axioms).
    """
    import pyoxigraph as ox  # noqa: PLC0415

    snapshot_path = Path(snapshot_path)
    db_path = config.db_path

    if (
        config.store_backend == "oxigraph"
        and db_path.exists()
        and any(db_path.iterdir())
        and not force
    ):
        raise KGStoreAlreadyExistsError(
            f"KG store already exists at {db_path}. Pass --force to overwrite."
        )

    handle = init_store(config, force=True)
    store = handle.raw

    try:
        nq_data = snapshot_path.read_bytes()
    except FileNotFoundError as exc:
        raise KGError(f"snapshot not found: {snapshot_path}") from exc
    except (PermissionError, IsADirectoryError, OSError) as exc:
        raise KGError(f"cannot read snapshot {snapshot_path}: {exc}") from exc

    count = 0
    for quad in ox.parse(nq_data, ox.RdfFormat.N_QUADS):
        store.add(quad)
        count += 1

    handle.close()
    return count


def list_snapshots(snapshot_dir: Path) -> list[SnapshotMeta]:
    """List all snapshots in a directory, sorted by timestamp descending."""
    snapshot_dir = Path(snapshot_dir)
    if not snapshot_dir.is_dir():
        return []

    metas: list[SnapshotMeta] = []
    for meta_file in sorted(snapshot_dir.glob("*.meta.json"), reverse=True):
        nq_file = meta_file.with_suffix("").with_suffix(".nq")
        if not nq_file.exists():
            continue
        raw = json.loads(meta_file.read_text(encoding="utf-8"))
        metas.append(
            SnapshotMeta(
                path=Path(raw.get("path", str(nq_file))),
                timestamp=raw.get("timestamp", ""),
                quad_count=raw.get("quad_count", 0),
                active_doc_types=raw.get("active_doc_types", []),
                store_backend=raw.get("store_backend", ""),
            )
        )
    return metas


__all__ = [
    "SnapshotMeta",
    "create_snapshot",
    "list_snapshots",
    "restore_snapshot",
]
