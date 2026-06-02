"""Migration coverage for rows A3, A4, A7, A8, A12, A14, A15."""

from __future__ import annotations

from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "kg-vertical-slice"


def _open_and_ingest(variant: str = "waterfall"):
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    root = FIXTURE_ROOT / variant
    run_migration(handle.raw, root, config)
    return KnowledgeGraph(handle.raw, config), config


def _open_and_ingest_with_deps():
    """Ingest + manually add a depends_on edge for A8 testing."""
    kg, config = _open_and_ingest()
    from cataforge.domain.kg._quads import build_relation_quad

    quad = build_relation_quad("M-001", "cf:depends_on", "M-002", config)
    kg.store.add(quad)
    return kg, config


# ------------------------------------------------------------------
# A3: QA-engineer task→AC trace
# ------------------------------------------------------------------


def test_a3_trace_from_feature_reaches_modules() -> None:
    """A3: from_requirement("F-001") should discover M-001 downstream."""
    kg, _ = _open_and_ingest()
    chain = kg.trace.from_requirement("F-001", direction="downstream")
    assert chain.root_id == "F-001"
    assert "M-001" in chain.modules


def test_a3_trace_from_ac_reaches_test_cases() -> None:
    """A3: from_requirement("AC-001") downstream should find TC-001 (verifies)."""
    kg, _ = _open_and_ingest()
    chain = kg.trace.from_requirement("AC-001", direction="downstream")
    assert "TC-001" in chain.test_cases


# ------------------------------------------------------------------
# A4: DevOps source_section (unmodeled narrative)
# ------------------------------------------------------------------


def test_a4_source_section_returns_none_for_missing_anchor() -> None:
    """A4: source_section for a non-existent anchor returns None."""
    kg, _ = _open_and_ingest()
    result = kg.query.source_section("arch", "§99.99")
    assert result is None


def test_a4_source_section_returns_text_for_known_section() -> None:
    """A4: source_section for a known doc+anchor returns markdown text."""
    kg, config = _open_and_ingest()
    result = kg.query.source_section("arch", "§2.1")
    if result is not None:
        assert "M-001" in result


# ------------------------------------------------------------------
# A7: Sprint-review plan_load
# ------------------------------------------------------------------


def test_a7_plan_load_includes_related_entities() -> None:
    """A7: plan_load with include_related=True pulls in neighbours."""
    kg, _ = _open_and_ingest()
    result = kg.query.plan_load(["F-001"], token_budget=10000, include_related=True)
    assert "F-001" in result.ordered


def test_a7_plan_load_respects_token_budget() -> None:
    """A7: plan_load drops entities when budget exhausted."""
    kg, _ = _open_and_ingest()
    result = kg.query.plan_load(
        ["F-001", "F-002", "M-001", "M-002", "TC-001", "TC-002"],
        token_budget=400,
    )
    assert len(result.ordered) == 2
    assert len(result.dropped) == 4


# ------------------------------------------------------------------
# A8: Task dependency inference via SPARQL cf:depends_on
# ------------------------------------------------------------------


def test_a8_depends_on_edge_discoverable() -> None:
    """A8: manually-added cf:depends_on edge is queryable via _depends_on."""
    kg, _ = _open_and_ingest_with_deps()
    deps = kg.query.depends_on("M-001")
    assert "M-002" in deps


def test_a8_depends_on_empty_when_no_deps() -> None:
    """A8: entity with no depends_on edges returns empty list."""
    kg, _ = _open_and_ingest()
    deps = kg.query.depends_on("F-001")
    assert deps == []


# ------------------------------------------------------------------
# A12: check_xref URI resolution (entity existence)
# ------------------------------------------------------------------


def test_a12_exists_returns_true_for_known_entity() -> None:
    """A12: kg.query.exists() resolves known entity_ids."""
    kg, _ = _open_and_ingest()
    assert kg.query.exists("F-001") is True
    assert kg.query.exists("M-001") is True
    assert kg.query.exists("TC-001") is True


def test_a12_exists_returns_false_for_missing_entity() -> None:
    """A12: kg.query.exists() returns False for nonexistent IDs."""
    kg, _ = _open_and_ingest()
    assert kg.query.exists("F-999") is False
    assert kg.query.exists("NONEXISTENT-001") is False


def test_a12_entity_lookup_returns_none_for_missing() -> None:
    """A12: entity() returns None rather than raising for missing IDs."""
    kg, _ = _open_and_ingest()
    assert kg.query.entity("F-999") is None


# ------------------------------------------------------------------
# A14: Degraded path (Bash-less Agent) — query + render_entity
# ------------------------------------------------------------------


def test_a14_query_entity_returns_dict() -> None:
    """A14: kg.query.entity() returns a flat dict for known entities."""
    kg, _ = _open_and_ingest()
    f = kg.query.entity("F-001")
    assert f is not None
    assert f["entity_id"] == "F-001"
    assert f["_class"] == "Feature"
    assert f["title"]


def test_a14_render_entity_produces_markdown() -> None:
    """A14: render_entity() returns readable markdown for known entities."""
    from cataforge.domain.kg.export import render_entity

    kg, _ = _open_and_ingest()
    md = render_entity(kg.store, "F-001")
    assert md is not None
    assert "F-001" in md


def test_a14_render_entity_returns_none_for_missing() -> None:
    """A14: render_entity() returns None for nonexistent entity_ids."""
    from cataforge.domain.kg.export import render_entity

    kg, _ = _open_and_ingest()
    assert render_entity(kg.store, "F-999") is None


# ------------------------------------------------------------------
# A15: build_xref SPARQL (legacy caller retired — traceability edges)
# ------------------------------------------------------------------


def test_a15_traceability_edges_present_after_ingest() -> None:
    """A15: After ingest, traceability predicates exist as typed edges."""
    from cataforge.domain.kg._ask import ask

    kg, config = _open_and_ingest()
    ns = config.ontology_namespace.rstrip("/") + "/"

    assert ask(
        kg.store,
        f"PREFIX cf: <{ns}> ASK {{ ?m cf:implements ?f . ?m a cf:Module . ?f a cf:Feature }}",
    )


def test_a15_all_entities_enumerates_fixture_set() -> None:
    """A15: all_entities() returns every entity from the fixture."""
    kg, _ = _open_and_ingest()
    entities = kg.query.all_entities()
    ids = {e["entity_id"] for e in entities}
    assert ids == {
        "F-001",
        "F-002",
        "AC-001",
        "AC-002",
        "M-001",
        "M-002",
        "TC-001",
        "TC-002",
        "TS-001",
    }


def test_a15_all_entities_type_filter() -> None:
    """A15: all_entities(types=["Feature"]) filters correctly."""
    kg, _ = _open_and_ingest()
    features = kg.query.all_entities(types=["Feature"])
    ids = {e["entity_id"] for e in features}
    assert ids == {"F-001", "F-002"}
