"""Entity-card rendering: source-section narrative and part_of relations."""

from __future__ import annotations

from pathlib import Path

from tests.kg._kg_fixtures import hx

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _ingested_store():
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, FIXTURE_ROOT / "waterfall", config)
    return handle


def _bare_entity_store():
    """Store holding one Feature entity with no Section node and no children."""
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.ingest.writer import write_project

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    project_iri = write_project(handle.raw, "proj-bare", "Bare", "waterfall", config)
    kg = KnowledgeGraph(handle.raw, config)
    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-001",
            class_name="Feature",
            title="Login",
            source_doc="prd",
            source_section="F-001 Login",
            content_hash=hx("h-f1"),
            project_iri=project_iri,
        )
    return handle


def _attach_own_narrative(handle, entity_id: str, text: str) -> None:
    import pyoxigraph as ox

    from cataforge.domain.kg import KGConfig
    from cataforge.domain.kg._sparql_utils import cf_namespace

    ns = cf_namespace(KGConfig(store_backend="memory"))
    entity_id_pred = ox.NamedNode(f"{ns}entity_id")
    subjects = [
        q.subject
        for q in handle.raw.quads_for_pattern(None, entity_id_pred, None, None)
        if q.object.value == entity_id
    ]
    assert subjects, f"entity {entity_id} not found in store"
    string_dt = ox.NamedNode("http://www.w3.org/2001/XMLSchema#string")
    handle.raw.add(
        ox.Quad(
            subjects[0],
            ox.NamedNode(f"{ns}narrative_body"),
            ox.Literal(text, datatype=string_dt),
        )
    )


class TestNarrativeBody:
    def test_feature_card_contains_source_section_narrative(self) -> None:
        from cataforge.domain.kg.export import render_entity

        handle = _ingested_store()
        card = render_entity(handle.raw, "F-001")
        assert card is not None
        assert "## Narrative" in card
        assert "允许已注册用户用邮箱 + 密码完成身份认证" in card

    def test_acceptance_criteria_card_contains_source_section_narrative(self) -> None:
        from cataforge.domain.kg.export import render_entity

        handle = _ingested_store()
        card = render_entity(handle.raw, "AC-001")
        assert card is not None
        assert "## Narrative" in card
        assert "输入合法 (邮箱, 密码) 对返回 200 + JWT" in card

    def test_entity_own_narrative_preferred_over_section_join(self) -> None:
        from cataforge.domain.kg.export import render_entity

        handle = _ingested_store()
        _attach_own_narrative(handle, "F-001", "实体自有正文优先")
        card = render_entity(handle.raw, "F-001")
        assert card is not None
        assert "## Narrative" in card
        assert "实体自有正文优先" in card
        assert "允许已注册用户用邮箱 + 密码完成身份认证" not in card

    def test_subordinate_own_narrative_preferred_over_parent_section(self) -> None:
        from cataforge.domain.kg.export import render_entity

        handle = _ingested_store()
        _attach_own_narrative(handle, "AC-001", "输入合法凭据返回 200 + JWT")
        card = render_entity(handle.raw, "AC-001")
        assert card is not None
        assert "## Narrative" in card
        assert "输入合法凭据返回 200 + JWT" in card
        assert "输入合法 (邮箱, 密码) 对返回 200 + JWT" not in card

    def test_card_without_section_node_omits_narrative_heading(self) -> None:
        from cataforge.domain.kg.export import render_entity

        handle = _bare_entity_store()
        card = render_entity(handle.raw, "F-001")
        assert card is not None
        assert "## Narrative" not in card


class TestPartOfRelations:
    def test_feature_card_lists_part_of_acceptance_criteria(self) -> None:
        from cataforge.domain.kg.export import render_entity

        handle = _ingested_store()
        card = render_entity(handle.raw, "F-001")
        assert card is not None
        assert "## Acceptance Criteria" in card
        assert "[AC-001](./AC-001.md)" in card

    def test_acceptance_criteria_card_lists_part_of_parent(self) -> None:
        from cataforge.domain.kg.export import render_entity

        handle = _ingested_store()
        card = render_entity(handle.raw, "AC-001")
        assert card is not None
        assert "## Part Of" in card
        assert "[F-001](./F-001.md)" in card


class TestRenderEntityCard:
    def test_flags_set_when_narrative_and_children_present(self) -> None:
        from cataforge.domain.kg.export import render_entity, render_entity_card

        handle = _ingested_store()
        card = render_entity_card(handle.raw, "F-001")
        assert card is not None
        assert card.has_narrative is True
        assert card.has_children is True
        assert card.markdown == render_entity(handle.raw, "F-001")

    def test_flags_clear_for_bare_entity(self) -> None:
        from cataforge.domain.kg.export import render_entity_card

        handle = _bare_entity_store()
        card = render_entity_card(handle.raw, "F-001")
        assert card is not None
        assert card.has_narrative is False
        assert card.has_children is False

    def test_unknown_entity_returns_none(self) -> None:
        from cataforge.domain.kg.export import render_entity_card

        handle = _ingested_store()
        assert render_entity_card(handle.raw, "F-999") is None
