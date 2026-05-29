"""Tests for TransactionContext high-level CRUD and facade write lock."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"

def _make_kg():
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.ingest.writer import write_project

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    project_iri = write_project(
        handle.raw, "proj-test", "Test Project", "waterfall", config
    )
    return KnowledgeGraph(handle.raw, config), config, project_iri

def _make_kg_with_entity():
    kg, config, project_iri = _make_kg()
    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-001",
            class_name="Feature",
            title="Login flow",
            source_doc="prd",
            source_section="F-001 Login flow",
            content_hash="abc123",
            project_iri=project_iri,
        )
    return kg, config, project_iri

# ------------------------------------------------------------------
# add_entity
# ------------------------------------------------------------------

def test_add_entity_creates_quads() -> None:
    kg, config, project_iri = _make_kg()

    with kg.transaction() as txn:
        iri = txn.add_entity(
            entity_id="F-001",
            class_name="Feature",
            title="Login flow",
            source_doc="prd",
            source_section="F-001 Login flow",
            content_hash="abc123",
            project_iri=project_iri,
        )

    assert iri == "https://cataforge.dev/instance/F-001"
    assert kg.query.exists("F-001")
    f = kg.query.feature("F-001")
    assert f is not None
    assert f["title"] == "Login flow"
    assert f["entity_id"] == "F-001"

def test_add_entity_idempotent_on_same_hash() -> None:
    kg, config, project_iri = _make_kg()

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-001",
            class_name="Feature",
            title="Login flow",
            source_doc="prd",
            source_section="F-001 Login flow",
            content_hash="abc123",
            project_iri=project_iri,
        )

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-001",
            class_name="Feature",
            title="Login flow",
            source_doc="prd",
            source_section="F-001 Login flow",
            content_hash="abc123",
            project_iri=project_iri,
        )
        assert txn.pending_inserts == 0
        assert txn.pending_deletes == 0

def test_add_entity_replaces_on_different_hash() -> None:
    kg, config, project_iri = _make_kg()

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-001",
            class_name="Feature",
            title="Login flow v1",
            source_doc="prd",
            source_section="F-001 Login flow v1",
            content_hash="hash_v1",
            project_iri=project_iri,
        )

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-001",
            class_name="Feature",
            title="Login flow v2",
            source_doc="prd",
            source_section="F-001 Login flow v2",
            content_hash="hash_v2",
            project_iri=project_iri,
        )

    f = kg.query.feature("F-001")
    assert f is not None
    assert f["title"] == "Login flow v2"

def test_add_entity_with_extra_slots() -> None:
    kg, config, project_iri = _make_kg()

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-001",
            class_name="Feature",
            title="Login",
            source_doc="prd",
            source_section="F-001 Login",
            content_hash="abc",
            project_iri=project_iri,
            extra_slots={"cf:priority": "high"},
        )

    from cataforge.domain.kg._ask import ask

    ns = config.ontology_namespace.rstrip("/") + "/"
    assert ask(
        kg.store,
        f'PREFIX cf: <{ns}> ASK {{ <https://cataforge.dev/instance/F-001> cf:priority "high" }}',
    )

# ------------------------------------------------------------------
# update_entity
# ------------------------------------------------------------------

def test_update_entity_partial_slot() -> None:
    kg, config, project_iri = _make_kg_with_entity()

    with kg.transaction() as txn:
        txn.update_entity("F-001", title="Updated title")

    f = kg.query.feature("F-001")
    assert f is not None
    assert f["title"] == "Updated title"
    assert f["source_doc"] == "prd"

def test_update_entity_with_content_hash_idempotent() -> None:
    kg, config, project_iri = _make_kg_with_entity()

    with kg.transaction() as txn:
        txn.update_entity("F-001", content_hash="abc123", title="Ignored")
        assert txn.pending_inserts == 0

def test_update_entity_not_found_raises() -> None:
    kg, config, project_iri = _make_kg()

    from cataforge.domain.kg import KGEntityNotFoundError

    with pytest.raises(KGEntityNotFoundError), kg.transaction() as txn:
        txn.update_entity("F-999", title="nope")

# ------------------------------------------------------------------
# delete_entity
# ------------------------------------------------------------------

def test_delete_entity_removes_all_quads() -> None:
    kg, config, project_iri = _make_kg_with_entity()

    with kg.transaction() as txn:
        txn.delete_entity("F-001")

    assert not kg.query.exists("F-001")

def test_delete_entity_not_found_raises() -> None:
    kg, config, project_iri = _make_kg()

    from cataforge.domain.kg import KGEntityNotFoundError

    with pytest.raises(KGEntityNotFoundError), kg.transaction() as txn:
        txn.delete_entity("F-999")

def test_delete_entity_without_cascade_rejects_incoming_edges() -> None:
    kg, config, project_iri = _make_kg_with_entity()

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="M-001",
            class_name="Module",
            title="Auth",
            source_doc="arch",
            source_section="M-001 Auth",
            content_hash="mod1",
            project_iri=project_iri,
        )

    with kg.transaction() as txn:
        txn.add_relation("M-001", "cf:implements", "F-001")

    from cataforge.domain.kg import KGValidationError

    with pytest.raises(KGValidationError, match="incoming edge"), kg.transaction() as txn:
        txn.delete_entity("F-001")

def test_delete_entity_with_cascade_removes_incoming_edges() -> None:
    kg, config, project_iri = _make_kg_with_entity()

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="M-001",
            class_name="Module",
            title="Auth",
            source_doc="arch",
            source_section="M-001 Auth",
            content_hash="mod1",
            project_iri=project_iri,
        )

    with kg.transaction() as txn:
        txn.add_relation("M-001", "cf:implements", "F-001")

    with kg.transaction() as txn:
        txn.delete_entity("F-001", cascade=True)

    assert not kg.query.exists("F-001")
    assert kg.query.exists("M-001")

# ------------------------------------------------------------------
# add_relation / remove_relation
# ------------------------------------------------------------------

def test_add_relation_creates_edge() -> None:
    kg, config, project_iri = _make_kg_with_entity()

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="M-001",
            class_name="Module",
            title="Auth",
            source_doc="arch",
            source_section="M-001 Auth",
            content_hash="mod1",
            project_iri=project_iri,
        )

    with kg.transaction() as txn:
        txn.add_relation("M-001", "cf:implements", "F-001")

    from cataforge.domain.kg._ask import ask

    ns = config.ontology_namespace.rstrip("/") + "/"
    assert ask(
        kg.store,
        f"ASK {{ <https://cataforge.dev/instance/M-001> "
        f"<{ns}implements> "
        f"<https://cataforge.dev/instance/F-001> }}",
    )

def test_add_relation_idempotent() -> None:
    kg, config, project_iri = _make_kg_with_entity()

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="M-001",
            class_name="Module",
            title="Auth",
            source_doc="arch",
            source_section="M-001 Auth",
            content_hash="mod1",
            project_iri=project_iri,
        )

    with kg.transaction() as txn:
        txn.add_relation("M-001", "cf:implements", "F-001")

    with kg.transaction() as txn:
        txn.add_relation("M-001", "cf:implements", "F-001")
        assert txn.pending_inserts == 0

def test_remove_relation() -> None:
    kg, config, project_iri = _make_kg_with_entity()

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="M-001",
            class_name="Module",
            title="Auth",
            source_doc="arch",
            source_section="M-001 Auth",
            content_hash="mod1",
            project_iri=project_iri,
        )

    with kg.transaction() as txn:
        txn.add_relation("M-001", "cf:implements", "F-001")

    with kg.transaction() as txn:
        txn.remove_relation("M-001", "cf:implements", "F-001")

    from cataforge.domain.kg._ask import ask

    ns = config.ontology_namespace.rstrip("/") + "/"
    assert not ask(
        kg.store,
        f"ASK {{ <https://cataforge.dev/instance/M-001> "
        f"<{ns}implements> "
        f"<https://cataforge.dev/instance/F-001> }}",
    )

# ------------------------------------------------------------------
# rollback behavior with high-level API
# ------------------------------------------------------------------

def test_rollback_discards_high_level_adds() -> None:
    kg, config, project_iri = _make_kg()

    with pytest.raises(RuntimeError, match="boom"), kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-099",
            class_name="Feature",
            title="Should not persist",
            source_doc="prd",
            source_section="F-099 test",
            content_hash="temp",
            project_iri=project_iri,
        )
        raise RuntimeError("boom")

    assert not kg.query.exists("F-099")

# ------------------------------------------------------------------
# write lock serialization
# ------------------------------------------------------------------

def test_write_lock_serializes_concurrent_transactions() -> None:
    kg, config, project_iri = _make_kg()
    order: list[str] = []
    barrier = threading.Barrier(2)

    def writer(entity_id: str, delay_name: str) -> None:
        barrier.wait()
        with kg.transaction() as txn:
            order.append(f"start-{delay_name}")
            txn.add_entity(
                entity_id=entity_id,
                class_name="Feature",
                title=delay_name,
                source_doc="prd",
                source_section=f"{entity_id} {delay_name}",
                content_hash=delay_name,
                project_iri=project_iri,
            )
            order.append(f"end-{delay_name}")

    t1 = threading.Thread(target=writer, args=("F-001", "first"))
    t2 = threading.Thread(target=writer, args=("F-002", "second"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert kg.query.exists("F-001")
    assert kg.query.exists("F-002")
    assert order[0].startswith("start-")
    assert order[1].startswith("end-")
    assert order[0].replace("start-", "") == order[1].replace("end-", "")
