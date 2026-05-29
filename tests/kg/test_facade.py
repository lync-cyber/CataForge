"""Smoke tests for the sub-PR 5 KnowledgeGraph facade.

Targets `QueryAPI`, `TraceAPI`, the synchronous `KnowledgeGraph`
context manager, and `render_entity()`. Exercises the same waterfall +
agile fixtures used by sub-PR 3 ingest tests so any divergence between
ingest and query surfaces shows up immediately.
"""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"
VARIANTS = ("waterfall", "agile")

def _open_and_ingest(variant: str):
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    root = FIXTURE_ROOT / variant
    run_migration(handle.raw, root, config)
    return KnowledgeGraph(handle.raw, config), config

@pytest.mark.parametrize("variant", VARIANTS)
def test_query_feature_returns_typed_dict(variant: str) -> None:
    kg, _ = _open_and_ingest(variant)
    f = kg.query.feature("F-001")
    assert f is not None
    assert f["entity_id"] == "F-001"
    assert f["_class"] == "Feature"
    assert f["sort_key"] == "F:000001"
    assert f["title"]

@pytest.mark.parametrize("variant", VARIANTS)
def test_query_module_component_typed_accessors(variant: str) -> None:
    kg, _ = _open_and_ingest(variant)
    m = kg.query.module("M-001")
    assert m is not None and m["_class"] == "Module"
    # Component / Page / API aren't in this fixture but the accessor
    # should at least return None cleanly rather than raising.
    assert kg.query.component("C-999") is None
    assert kg.query.api("API-999") is None
    assert kg.query.page("P-999") is None

@pytest.mark.parametrize("variant", VARIANTS)
def test_query_entity_ids_diff_against_filesystem(variant: str) -> None:
    kg, _ = _open_and_ingest(variant)
    ids = kg.query.entity_ids()
    assert ids == {
        "F-001", "F-002",
        "AC-001", "AC-002",
        "M-001", "M-002",
        "TC-001", "TC-002",
        "TS-001",
    }

@pytest.mark.parametrize("variant", VARIANTS)
def test_query_exists(variant: str) -> None:
    kg, _ = _open_and_ingest(variant)
    assert kg.query.exists("F-001") is True
    assert kg.query.exists("F-999") is False

@pytest.mark.parametrize("variant", VARIANTS)
def test_trace_bidirectional_coverage_detects_impl(variant: str) -> None:
    kg, _ = _open_and_ingest(variant)
    rows = kg.trace.bidirectional_coverage()
    by_id = {r.feature_id: r for r in rows}
    assert "F-001" in by_id and "F-002" in by_id
    # Fixture has Module cf:implements F-001 and F-002, so has_impl=True.
    assert by_id["F-001"].has_impl is True
    assert by_id["F-002"].has_impl is True

@pytest.mark.parametrize("variant", VARIANTS)
def test_trace_from_requirement_downstream(variant: str) -> None:
    kg, _ = _open_and_ingest(variant)
    chain = kg.trace.from_requirement("F-001", direction="downstream")
    assert chain.root_id == "F-001"
    assert "M-001" in chain.modules

@pytest.mark.parametrize("variant", VARIANTS)
def test_render_entity_produces_markdown(variant: str) -> None:
    from cataforge.domain.kg.export import render_entity

    kg, _ = _open_and_ingest(variant)
    md = render_entity(kg.store, "F-001")
    assert md is not None
    assert "F-001" in md
    # Unknown entity returns None rather than raising.
    assert render_entity(kg.store, "F-999") is None

def test_transaction_commit_and_rollback() -> None:
    import pyoxigraph as ox

    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    kg = KnowledgeGraph(handle.raw, config)

    quad = ox.Quad(
        ox.NamedNode("https://cataforge.dev/instance/F-101"),
        ox.NamedNode("https://cataforge.dev/ontology/title"),
        ox.Literal("smoke"),
    )

    with kg.transaction() as txn:
        txn.add(quad)
    assert any(
        kg.store.quads_for_pattern(quad.subject, None, None, None)
    )

    quad2 = ox.Quad(
        ox.NamedNode("https://cataforge.dev/instance/F-102"),
        ox.NamedNode("https://cataforge.dev/ontology/title"),
        ox.Literal("rollback"),
    )
    with pytest.raises(RuntimeError, match="boom"), kg.transaction() as txn:
        txn.add(quad2)
        raise RuntimeError("boom")
    assert not list(kg.store.quads_for_pattern(quad2.subject, None, None, None))

# ------------------------------------------------------------------
# Q1 — QueryAPI.api() / .page() typed accessors (hit path)
# ------------------------------------------------------------------

def _make_kg_with_project():
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.ingest.writer import write_project

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    project_iri = write_project(
        handle.raw, "proj-test", "Test", "waterfall", config
    )
    return KnowledgeGraph(handle.raw, config), config, project_iri

def test_query_api_typed_accessor_returns_dict() -> None:
    kg, config, project_iri = _make_kg_with_project()
    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="API-001",
            class_name="API",
            title="POST /login",
            source_doc="arch",
            source_section="API-001 POST /login",
            content_hash="api001hash",
            project_iri=project_iri,
        )

    result = kg.query.api("API-001")
    assert result is not None
    assert result["_class"] == "API"
    assert result["entity_id"] == "API-001"
    assert result["title"] == "POST /login"

    assert kg.query.api("API-999") is None

def test_query_page_typed_accessor_returns_dict() -> None:
    kg, config, project_iri = _make_kg_with_project()
    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="P-001",
            class_name="Page",
            title="Dashboard",
            source_doc="ui-spec",
            source_section="P-001 Dashboard",
            content_hash="p001hash",
            project_iri=project_iri,
        )

    result = kg.query.page("P-001")
    assert result is not None
    assert result["_class"] == "Page"
    assert result["entity_id"] == "P-001"
    assert result["title"] == "Dashboard"

    assert kg.query.page("P-999") is None

# ------------------------------------------------------------------
# Q2 — QueryAPI.depends_on() public + TraceAPI.stale_dependencies()
# ------------------------------------------------------------------

def test_depends_on_returns_dependency_ids() -> None:
    kg, config, project_iri = _make_kg_with_project()
    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="M-001",
            class_name="Module",
            title="Auth",
            source_doc="arch",
            source_section="M-001 Auth",
            content_hash="m001hash",
            project_iri=project_iri,
        )
        txn.add_entity(
            entity_id="M-002",
            class_name="Module",
            title="Session",
            source_doc="arch",
            source_section="M-002 Session",
            content_hash="m002hash",
            project_iri=project_iri,
        )
        txn.add_relation("M-001", "cf:depends_on", "M-002")

    deps = kg.query.depends_on("M-001")
    assert deps == ["M-002"]

def test_depends_on_empty_when_no_edges() -> None:
    kg, config, project_iri = _make_kg_with_project()
    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-001",
            class_name="Feature",
            title="Login",
            source_doc="prd",
            source_section="F-001 Login",
            content_hash="f001hash",
            project_iri=project_iri,
        )

    deps = kg.query.depends_on("F-001")
    assert deps == []

def test_stale_dependencies_empty_on_matching_hashes() -> None:
    kg, config, project_iri = _make_kg_with_project()
    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="M-001",
            class_name="Module",
            title="Auth",
            source_doc="arch",
            source_section="M-001 Auth",
            content_hash="same_hash",
            project_iri=project_iri,
        )
        txn.add_entity(
            entity_id="M-002",
            class_name="Module",
            title="Session",
            source_doc="arch",
            source_section="M-002 Session",
            content_hash="same_hash",
            project_iri=project_iri,
        )
        txn.add_relation("M-001", "cf:depends_on", "M-002")

    stale = kg.trace.stale_dependencies()
    assert stale == []

def test_stale_dependencies_detects_hash_mismatch() -> None:
    kg, config, project_iri = _make_kg_with_project()
    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="M-001",
            class_name="Module",
            title="Auth",
            source_doc="arch",
            source_section="M-001 Auth",
            content_hash="hash_aaa",
            project_iri=project_iri,
        )
        txn.add_entity(
            entity_id="M-002",
            class_name="Module",
            title="Session",
            source_doc="arch",
            source_section="M-002 Session",
            content_hash="hash_bbb",
            project_iri=project_iri,
        )
        txn.add_relation("M-001", "cf:depends_on", "M-002")

    stale = kg.trace.stale_dependencies()
    assert len(stale) == 1
    assert stale[0] == ("M-001", "M-002")

@pytest.mark.parametrize("variant", VARIANTS)
def test_stale_dependencies_empty_on_clean_fixture(variant: str) -> None:
    kg, _ = _open_and_ingest(variant)
    stale = kg.trace.stale_dependencies()
    assert stale == []
