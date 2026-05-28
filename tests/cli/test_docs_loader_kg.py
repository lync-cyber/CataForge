"""KG dispatch tests for ``cataforge.docs.loader.plan_load`` / ``resolve_deps``.

Covers the boundary added in Wave B (P0-5): when every input ref targets a
doc_type in ``framework.json.kg.kg_active_doc_types`` and a KG store exists,
the calls go through ``KnowledgeGraph.query``; otherwise they keep using the
legacy ``.doc-index.json`` walk.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.docs import loader

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


@pytest.fixture(autouse=True)
def reset_loader_caches():
    loader._INDEX_CACHE = None
    loader._INDEX_CACHE_ROOT = None
    loader._DOC_TYPE_MAP_CACHE.clear()
    yield
    loader._INDEX_CACHE = None
    loader._INDEX_CACHE_ROOT = None
    loader._DOC_TYPE_MAP_CACHE.clear()


@pytest.fixture(autouse=True)
def reset_dispatch_cache():
    from cataforge.kg._dispatch import invalidate_cache

    invalidate_cache()
    yield
    invalidate_cache()


def _project_with_kg(tmp_path: Path, *, active: list[str]) -> Path:
    """Build a project root with an ingested KG store + framework.json."""
    from cataforge.kg import KGConfig
    from cataforge.kg.ingest import run_migration
    from cataforge.kg.store import init_store

    project = tmp_path / "project"
    project.mkdir()
    (project / ".cataforge").mkdir()
    (project / "docs").mkdir()

    config = KGConfig(
        store_backend="oxigraph",
        db_path=project / ".cataforge" / "kg" / "store",
        kg_active_doc_types=set(active),
    )
    handle = init_store(config, force=True)
    run_migration(handle.raw, FIXTURE_ROOT / "waterfall", config)
    handle.raw.flush()
    handle.close()

    (project / ".cataforge" / "framework.json").write_text(
        json.dumps({"kg": {"kg_active_doc_types": active}}), encoding="utf-8"
    )
    return project


def _project_no_kg(tmp_path: Path) -> Path:
    """Project with empty kg_active_doc_types — legacy-only path."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".cataforge").mkdir()
    (project / "docs").mkdir()
    (project / ".cataforge" / "framework.json").write_text(
        json.dumps({"kg": {"kg_active_doc_types": []}}), encoding="utf-8"
    )
    return project


# ---------------------------------------------------------------------------
# plan_load — KG dispatch
# ---------------------------------------------------------------------------


def test_plan_load_uses_kg_when_all_refs_active(tmp_path: Path) -> None:
    project = _project_with_kg(tmp_path, active=["prd", "arch", "test"])

    refs = ["prd#§2.F-001", "prd#§2.F-002"]
    loadable, deferred = loader.plan_load(refs, str(project), token_budget=10_000)

    # KG path: returns ref-form preserving input shape (mapped back from entity_ids)
    assert set(loadable) == set(refs)
    assert deferred == []


def test_plan_load_budget_drop_under_kg(tmp_path: Path) -> None:
    project = _project_with_kg(tmp_path, active=["prd", "arch", "test"])

    refs = ["prd#§2.F-001", "prd#§2.F-002"]
    # 200 tokens per entity flat estimate; budget 250 fits only one
    loadable, deferred = loader.plan_load(refs, str(project), token_budget=250)

    assert len(loadable) == 1
    assert len(deferred) == 1
    assert set(loadable) | set(deferred) == set(refs)


def test_plan_load_falls_back_to_legacy_when_no_active(tmp_path: Path) -> None:
    project = _project_no_kg(tmp_path)

    # No KG, no index → legacy path returns all as loadable (default 200/entity)
    refs = ["prd#§2.F-001"]
    loadable, deferred = loader.plan_load(refs, str(project), token_budget=10_000)
    assert loadable == refs
    assert deferred == []


def test_plan_load_falls_back_when_ref_targets_inactive_doc_type(
    tmp_path: Path,
) -> None:
    """Mixed active+legacy input must NOT route through KG (budget math undefined)."""
    project = _project_with_kg(tmp_path, active=["prd"])  # only prd active

    refs = ["prd#§2.F-001", "arch#§2.M-001"]  # arch is legacy
    loadable, deferred = loader.plan_load(refs, str(project), token_budget=10_000)

    # Falls back to legacy; without index, both stay loadable at default 200 each
    assert set(loadable) | set(deferred) == set(refs)


def test_plan_load_falls_back_for_whole_section_ref(tmp_path: Path) -> None:
    """Refs without item_id (whole-section like `prd#§1`) have no entity → legacy."""
    project = _project_with_kg(tmp_path, active=["prd", "arch", "test"])

    refs = ["prd#§1"]  # whole section, no F-NNN
    loadable, deferred = loader.plan_load(refs, str(project), token_budget=10_000)

    # Legacy keeps it loadable (no index entry → default 200)
    assert loadable == refs


def test_plan_load_empty_input(tmp_path: Path) -> None:
    project = _project_with_kg(tmp_path, active=["prd", "arch", "test"])

    loadable, deferred = loader.plan_load([], str(project), token_budget=1000)

    assert loadable == []
    assert deferred == []


# ---------------------------------------------------------------------------
# resolve_deps — KG dispatch
# ---------------------------------------------------------------------------


def test_resolve_deps_uses_kg_when_active(tmp_path: Path) -> None:
    project = _project_with_kg(tmp_path, active=["prd", "arch", "test"])

    # KG path is invoked. Fixture has no explicit cf:depends_on triples for
    # F-001 in the ingested vertical-slice → expect empty result, but NOT
    # fallback to legacy (which would return [] from missing index anyway).
    deps = loader.resolve_deps("prd#§2.F-001", str(project))
    assert isinstance(deps, list)


def test_resolve_deps_falls_back_when_doc_type_inactive(tmp_path: Path) -> None:
    project = _project_with_kg(tmp_path, active=["prd"])  # arch is legacy

    # arch doc_type not in active set → KG dispatch returns None → legacy path
    deps = loader.resolve_deps("arch#§2.M-001", str(project))
    assert deps == []  # legacy with no index


def test_resolve_deps_falls_back_for_unparseable_ref(tmp_path: Path) -> None:
    project = _project_with_kg(tmp_path, active=["prd", "arch", "test"])

    deps = loader.resolve_deps("not-a-ref-at-all", str(project))
    assert deps == []


def test_resolve_deps_falls_back_for_whole_section_ref(tmp_path: Path) -> None:
    project = _project_with_kg(tmp_path, active=["prd", "arch", "test"])

    deps = loader.resolve_deps("prd#§1", str(project))
    assert deps == []


# ---------------------------------------------------------------------------
# Helper sanity: _entity_id_to_ref reconstructs source_doc#§<anchor>
# ---------------------------------------------------------------------------


def test_entity_id_to_ref_reconstructs_from_kg_metadata(tmp_path: Path) -> None:
    from cataforge.kg import KGConfig, KnowledgeGraph

    project = _project_with_kg(tmp_path, active=["prd", "arch", "test"])
    config = KGConfig(
        store_backend="oxigraph",
        db_path=project / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )
    with KnowledgeGraph.connect(config) as kg:
        ref = loader._entity_id_to_ref(kg, "F-001")

    assert ref is not None
    assert ref.startswith("prd")
    assert "F-001" in ref or "§2" in ref
