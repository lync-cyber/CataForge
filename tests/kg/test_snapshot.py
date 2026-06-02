"""Tests for KG snapshot and rollback."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _make_populated_store():
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, FIXTURE_ROOT / "waterfall", config)
    return handle, config


def _count_quads(store) -> int:
    return sum(1 for _ in store.quads_for_pattern(None, None, None, None))


def test_snapshot_roundtrip(tmp_path: Path) -> None:
    handle, config = _make_populated_store()
    original_count = _count_quads(handle.raw)
    assert original_count > 0

    from cataforge.domain.kg.snapshot import create_snapshot, restore_snapshot

    meta = create_snapshot(handle.raw, config, tmp_path / "snapshots")
    assert meta.quad_count == original_count
    assert meta.path.exists()
    assert meta.path.suffix == ".nq"
    assert meta.path.with_suffix(".meta.json").exists()

    from cataforge.domain.kg import KGConfig

    restore_config = KGConfig(store_backend="oxigraph", db_path=tmp_path / "restored-store")
    restored_count = restore_snapshot(meta.path, restore_config, force=True)
    assert restored_count == original_count


def test_snapshot_meta_fields(tmp_path: Path) -> None:
    import json

    handle, config = _make_populated_store()

    from cataforge.domain.kg.snapshot import create_snapshot

    meta = create_snapshot(handle.raw, config, tmp_path / "snapshots", label="test-label")

    assert "test-label" in meta.path.name
    assert meta.timestamp
    assert meta.quad_count > 0
    assert meta.active_doc_types == sorted(config.kg_active_doc_types)
    assert meta.store_backend == "memory"

    meta_json = json.loads(meta.path.with_suffix(".meta.json").read_text(encoding="utf-8"))
    assert meta_json["quad_count"] == meta.quad_count
    assert meta_json["timestamp"] == meta.timestamp


def test_rollback_refuses_without_force(tmp_path: Path) -> None:
    handle, config = _make_populated_store()

    from cataforge.domain.kg import KGConfig, KGStoreAlreadyExistsError
    from cataforge.domain.kg.snapshot import create_snapshot, restore_snapshot

    meta = create_snapshot(handle.raw, config, tmp_path / "snapshots")

    db_path = tmp_path / "existing-store"
    existing_config = KGConfig(store_backend="oxigraph", db_path=db_path)
    from cataforge.domain.kg import init_store

    init_store(existing_config, force=True).close()

    with pytest.raises(KGStoreAlreadyExistsError):
        restore_snapshot(meta.path, existing_config, force=False)


def test_list_snapshots_sorted(tmp_path: Path) -> None:
    import time

    handle, config = _make_populated_store()

    from cataforge.domain.kg.snapshot import create_snapshot, list_snapshots

    snap_dir = tmp_path / "snapshots"
    create_snapshot(handle.raw, config, snap_dir, label="first")
    time.sleep(0.01)
    create_snapshot(handle.raw, config, snap_dir, label="second")

    snapshots = list_snapshots(snap_dir)
    assert len(snapshots) == 2
    assert snapshots[0].timestamp >= snapshots[1].timestamp


def test_snapshot_empty_store(tmp_path: Path) -> None:
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.snapshot import create_snapshot

    config = KGConfig(store_backend="memory", kg_active_doc_types=set())
    handle = init_store(config, force=True)

    meta = create_snapshot(handle.raw, config, tmp_path / "snapshots")
    assert meta.quad_count > 0  # bootstrap axioms are still present


def test_list_snapshots_empty_dir(tmp_path: Path) -> None:
    from cataforge.domain.kg.snapshot import list_snapshots

    assert list_snapshots(tmp_path / "nonexistent") == []


def test_snapshot_label_sanitization(tmp_path: Path) -> None:
    handle, config = _make_populated_store()

    from cataforge.domain.kg.snapshot import create_snapshot

    meta = create_snapshot(handle.raw, config, tmp_path / "snapshots", label="my label/v2")
    assert " " not in meta.path.name
    assert "/" not in meta.path.name
