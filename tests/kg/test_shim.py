"""Shim layer per-doc_type dispatch tests.

Verifies each public shim in :mod:`cataforge.domain.kg._shim`:

* with an active doc_type → KG branch returns a typed dict
* with no active doc_type → legacy branch delegates to
  :mod:`cataforge.domain.docs.loader` / :mod:`cataforge.domain.docs.indexer`

Tests inject an already-open `KnowledgeGraph` via the `kg=...`
parameter; the production `db_path` path is exercised via a
small oxigraph-backed roundtrip in the last test.
"""
from __future__ import annotations

import warnings
from dataclasses import replace
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"

def _ingest_into_memory(project_root: Path):
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, project_root, config)
    kg = KnowledgeGraph(handle.raw, config)
    return kg, config

def _active(config, doc_types: set[str]):
    return replace(config, kg_active_doc_types=doc_types)

# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------

def test_extract_kg_branch() -> None:
    from cataforge.domain.kg._shim import extract

    project_root = FIXTURE_ROOT / "waterfall"
    kg, base_config = _ingest_into_memory(project_root)
    config = _active(base_config, {"prd"})

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        # section_id carries the entity_id token; shim parses it out.
        result = extract(
            "prd",
            "§2.F-001",
            project_root=project_root,
            config=config,
            kg=kg,
        )

    assert result is not None
    assert result["entity_id"] == "F-001"
    assert result["_class"] == "Feature"
    assert result["doc_type"] == "prd"

def test_extract_legacy_branch_is_invoked_when_doc_type_inactive(tmp_path: Path) -> None:
    """When the doc_type isn't in `kg_active_doc_types`, the shim must
    delegate to :mod:`cataforge.domain.docs.loader` (not the KG).

    The fixture's heading style (``## §1 概览``) is not loader-friendly
    by itself, so we synthesize a tiny project on `tmp_path` with a
    legacy-loader-compatible heading and confirm the legacy branch
    surfaces the body text.
    """
    from cataforge.domain.kg._shim import extract

    project_root = tmp_path / "proj"
    (project_root / "docs" / "brief").mkdir(parents=True)
    (project_root / ".cataforge").mkdir(parents=True)
    (project_root / ".cataforge" / "framework.json").write_text(
        '{"docs": {"doc_types": {"brief": "brief"}}}',
        encoding="utf-8",
    )
    (project_root / "docs" / "brief" / "brief-main.md").write_text(
        "---\nid: brief\n---\n\n## 1 Overview\n\nlegacy body\n",
        encoding="utf-8",
    )

    # No KG store on disk; doc_type "brief" not in active set → legacy.
    from cataforge.domain.kg import KGConfig

    config = KGConfig(
        store_backend="oxigraph",
        db_path=project_root / ".cataforge" / "kg" / "store",
        kg_active_doc_types=set(),
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = extract(
            "brief",
            "§1",
            project_root=project_root,
            config=config,
        )

    assert result is not None
    assert result["doc_type"] == "brief"
    assert result["_class"] is None, "legacy branch leaves _class unset"
    assert result.get("body"), "legacy branch must populate body text"
    assert "legacy body" in result["body"]

# ---------------------------------------------------------------------------
# extract_batch
# ---------------------------------------------------------------------------

def test_extract_batch_dispatches_per_spec() -> None:
    from cataforge.domain.kg._shim import extract_batch

    project_root = FIXTURE_ROOT / "waterfall"
    kg, base_config = _ingest_into_memory(project_root)
    config = _active(base_config, {"prd"})

    specs = [
        {"doc_type": "prd", "section_id": "§2.F-001"},
        {"doc_type": "prd", "section_id": "§2.F-002"},
    ]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        results = extract_batch(
            specs, project_root=project_root, config=config, kg=kg
        )

    assert len(results) == 2
    eids = {r["entity_id"] for r in results}
    assert eids == {"F-001", "F-002"}

# ---------------------------------------------------------------------------
# plan_load
# ---------------------------------------------------------------------------

def test_plan_load_kg_branch_orders_entities() -> None:
    from cataforge.domain.kg._shim import plan_load

    project_root = FIXTURE_ROOT / "waterfall"
    kg, base_config = _ingest_into_memory(project_root)
    config = _active(base_config, {"prd", "arch", "test"})

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = plan_load(
            ["F-001", "F-002"],
            10_000,
            project_root=project_root,
            config=config,
            kg=kg,
        )

    assert set(result["ordered"]) >= {"F-001", "F-002"}
    assert result["dropped"] == []
    assert result["estimated_tokens"] > 0

def test_plan_load_drops_when_budget_exhausted() -> None:
    from cataforge.domain.kg._shim import plan_load

    project_root = FIXTURE_ROOT / "waterfall"
    kg, base_config = _ingest_into_memory(project_root)
    config = _active(base_config, {"prd"})

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = plan_load(
            ["F-001", "F-002"],
            100,
            project_root=project_root,
            config=config,
            kg=kg,
        )

    # Budget = 100, per-entity estimate = 200 → nothing fits.
    assert result["ordered"] == []
    assert "F-001" in result["dropped"]

# ---------------------------------------------------------------------------
# build_full_index
# ---------------------------------------------------------------------------

def test_build_full_index_kg_branch() -> None:
    from cataforge.domain.kg._shim import build_full_index

    project_root = FIXTURE_ROOT / "waterfall"
    kg, base_config = _ingest_into_memory(project_root)
    config = _active(base_config, {"prd", "arch", "test"})

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        index = build_full_index(
            project_root=project_root, config=config, kg=kg
        )

    assert set(index.keys()) >= {"F-001", "F-002", "M-001", "TC-001"}
    f001 = index["F-001"]
    assert f001["_class"] == "Feature"
    assert f001["sort_key"] == "F:000001"

# ---------------------------------------------------------------------------
# resolve_deps
# ---------------------------------------------------------------------------

def test_resolve_deps_kg_branch_empty_when_none_declared() -> None:
    from cataforge.domain.kg._shim import resolve_deps

    project_root = FIXTURE_ROOT / "waterfall"
    kg, base_config = _ingest_into_memory(project_root)
    config = _active(base_config, {"prd"})

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        deps = resolve_deps(
            "F-001", project_root=project_root, config=config, kg=kg
        )

    assert deps == []

# ---------------------------------------------------------------------------
# extract_with_body
# ---------------------------------------------------------------------------

def test_extract_with_body_renders_via_kg() -> None:
    from cataforge.domain.kg._shim import extract_with_body

    project_root = FIXTURE_ROOT / "waterfall"
    kg, base_config = _ingest_into_memory(project_root)
    config = _active(base_config, {"prd"})

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        record = extract_with_body(
            "prd",
            "§2.F-001",
            project_root=project_root,
            config=config,
            kg=kg,
        )

    assert record is not None
    assert record["entity_id"] == "F-001"
    assert record.get("body"), "KG branch must render body via render_entity()"
    assert "F-001" in record["body"]

# ---------------------------------------------------------------------------
# source_section
# ---------------------------------------------------------------------------

def test_source_section_legacy_branch_slices_file() -> None:
    from cataforge.domain.kg._shim import source_section

    project_root = FIXTURE_ROOT / "waterfall"
    kg, base_config = _ingest_into_memory(project_root)
    config = _active(base_config, set())  # legacy fallback

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        section = source_section(
            "prd",
            "§1",
            project_root=project_root,
            config=config,
            kg=kg,
        )

    assert section is not None
    assert "§1" in section

# ---------------------------------------------------------------------------
# DeprecationWarning emission
# ---------------------------------------------------------------------------

def test_shim_emits_deprecation_warning() -> None:
    from cataforge.domain.kg._shim import build_full_index

    project_root = FIXTURE_ROOT / "waterfall"
    kg, base_config = _ingest_into_memory(project_root)
    config = _active(base_config, {"prd"})

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        build_full_index(project_root=project_root, config=config, kg=kg)

    deps = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deps, "expected at least one DeprecationWarning"
    assert any("build_full_index" in str(w.message) for w in deps)

# ---------------------------------------------------------------------------
# Transient connection (oxigraph backend, full lifecycle)
# ---------------------------------------------------------------------------

def test_extract_transient_connection_oxigraph(tmp_path: Path) -> None:
    """End-to-end smoke without an injected `kg=...` handle.

    Exercises the production code path where the shim opens its own
    connection from `config.db_path`. Requires the oxigraph backend
    because memory stores are not shared across `connect()` calls.

    The RocksDB instance only permits one open writer at a time; the
    setup handle must be released (via `del` + `gc.collect`) before
    the shim can open a second connection on the same path.
    """
    import gc

    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg._shim import extract
    from cataforge.domain.kg.ingest import run_migration

    project_root = FIXTURE_ROOT / "waterfall"
    db_path = tmp_path / ".cataforge" / "kg" / "store"
    config = KGConfig(
        store_backend="oxigraph",
        db_path=db_path,
        kg_active_doc_types={"prd"},
    )
    handle = init_store(config, force=True)
    run_migration(handle.raw, project_root, config)
    del handle
    gc.collect()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        result = extract(
            "prd",
            "§2.F-001",
            project_root=project_root,
            config=config,
        )

    assert result is not None
    assert result["entity_id"] == "F-001"
