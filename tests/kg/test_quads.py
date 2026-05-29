"""Unit tests for _quads.py quad construction helpers."""
from __future__ import annotations


def _config():
    from cataforge.domain.kg import KGConfig

    return KGConfig(store_backend="memory")

def test_build_entity_quads_count_and_iri() -> None:
    from cataforge.domain.kg._quads import build_entity_quads

    config = _config()
    quads = build_entity_quads(
        entity_id="F-001",
        class_name="Feature",
        title="Login",
        source_doc="prd",
        source_section="F-001 Login",
        content_hash="abc",
        project_iri="https://cataforge.dev/instance/proj-test",
        config=config,
        mtime=0.0,
    )
    assert len(quads) == 9
    subjects = {str(q.subject.value) for q in quads}
    assert subjects == {"https://cataforge.dev/instance/F-001"}

    predicates = {str(q.predicate.value) for q in quads}
    ns = config.ontology_namespace.rstrip("/") + "/"
    assert f"{ns}entity_id" in predicates
    assert f"{ns}title" in predicates
    assert f"{ns}content_hash" in predicates
    assert f"{ns}sort_key" in predicates
    assert f"{ns}updated_at" in predicates
    assert f"{ns}belongs_to_project" in predicates

def test_build_entity_quads_with_extras() -> None:
    from cataforge.domain.kg._quads import build_entity_quads

    config = _config()
    quads = build_entity_quads(
        entity_id="F-001",
        class_name="Feature",
        title="Login",
        source_doc="prd",
        source_section="F-001 Login",
        content_hash="abc",
        project_iri="https://cataforge.dev/instance/proj-test",
        config=config,
        extra_slots={"cf:priority": "high", "cf:status": "open"},
    )
    assert len(quads) == 11

def test_build_relation_quad_iri() -> None:
    from cataforge.domain.kg._quads import build_relation_quad

    config = _config()
    quad = build_relation_quad("M-001", "cf:implements", "F-001", config)
    assert str(quad.subject.value) == "https://cataforge.dev/instance/M-001"
    assert str(quad.object.value) == "https://cataforge.dev/instance/F-001"
    ns = config.ontology_namespace.rstrip("/") + "/"
    assert str(quad.predicate.value) == f"{ns}implements"

def test_quads_for_subject_returns_all() -> None:
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg._quads import build_entity_quads, quads_for_subject

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    store = handle.raw

    quads = build_entity_quads(
        entity_id="F-001",
        class_name="Feature",
        title="Login",
        source_doc="prd",
        source_section="F-001 Login",
        content_hash="abc",
        project_iri="https://cataforge.dev/instance/proj-test",
        config=config,
    )
    for q in quads:
        store.add(q)

    retrieved = quads_for_subject(store, "https://cataforge.dev/instance/F-001")
    assert len(retrieved) == len(quads)

def test_quads_targeting_returns_incoming() -> None:
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg._quads import (
        build_entity_quads,
        build_relation_quad,
        quads_targeting,
    )

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    store = handle.raw

    for eid, cls in [("F-001", "Feature"), ("M-001", "Module")]:
        for q in build_entity_quads(
            entity_id=eid,
            class_name=cls,
            title=eid,
            source_doc="prd",
            source_section=f"{eid} test",
            content_hash=f"hash-{eid}",
            project_iri="https://cataforge.dev/instance/proj-test",
            config=config,
        ):
            store.add(q)

    rel = build_relation_quad("M-001", "cf:implements", "F-001", config)
    store.add(rel)

    incoming = quads_targeting(store, "https://cataforge.dev/instance/F-001")
    assert len(incoming) >= 1
    pred_values = {str(q.predicate.value) for q in incoming}
    ns = config.ontology_namespace.rstrip("/") + "/"
    assert f"{ns}implements" in pred_values
