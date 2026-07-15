"""Tests for TransactionContext high-level CRUD and facade write lock."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from tests.kg._kg_fixtures import hx

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _make_kg():
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.ingest.writer import write_project

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    project_iri = write_project(handle.raw, "proj-test", "Test Project", "waterfall", config)
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
            content_hash=hx("abc123"),
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
            content_hash=hx("abc123"),
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
            content_hash=hx("abc123"),
            project_iri=project_iri,
        )

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-001",
            class_name="Feature",
            title="Login flow",
            source_doc="prd",
            source_section="F-001 Login flow",
            content_hash=hx("abc123"),
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
            content_hash=hx("hash_v1"),
            project_iri=project_iri,
        )

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="F-001",
            class_name="Feature",
            title="Login flow v2",
            source_doc="prd",
            source_section="F-001 Login flow v2",
            content_hash=hx("hash_v2"),
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
            content_hash=hx("abc"),
            project_iri=project_iri,
            extra_slots={"cf:priority": "high"},
        )

    from cataforge.domain.kg._ask import ask

    ns = config.ontology_namespace.rstrip("/") + "/"
    assert ask(
        kg.store,
        f'PREFIX cf: <{ns}> ASK {{ <https://cataforge.dev/instance/F-001> cf:priority "high" }}',
    )


def test_add_entity_with_parent_scopes_iri_and_part_of() -> None:
    kg, config, project_iri = _make_kg_with_entity()

    with kg.transaction() as txn:
        iri = txn.add_entity(
            entity_id="AC-001",
            class_name="AcceptanceCriteria",
            title="登录验收",
            source_doc="prd",
            source_section="AC-001 登录验收",
            content_hash=hx("acc1"),
            project_iri=project_iri,
            parent_id="F-001",
        )

    assert iri == "https://cataforge.dev/instance/F-001/AC-001"

    from cataforge.domain.kg._ask import ask

    ns = config.ontology_namespace.rstrip("/") + "/"
    assert ask(
        kg.store,
        f"ASK {{ <{iri}> <{ns}part_of> <https://cataforge.dev/instance/F-001> }}",
    )


def test_add_entity_with_parent_idempotent_on_same_hash() -> None:
    kg, config, project_iri = _make_kg_with_entity()

    for _ in range(2):
        with kg.transaction() as txn:
            txn.add_entity(
                entity_id="AC-001",
                class_name="AcceptanceCriteria",
                title="登录验收",
                source_doc="prd",
                source_section="AC-001 登录验收",
                content_hash=hx("acc1"),
                project_iri=project_iri,
                parent_id="F-001",
            )

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="AC-001",
            class_name="AcceptanceCriteria",
            title="登录验收",
            source_doc="prd",
            source_section="AC-001 登录验收",
            content_hash=hx("acc1"),
            project_iri=project_iri,
            parent_id="F-001",
        )
        assert txn.pending_inserts == 0
        assert txn.pending_deletes == 0


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
        txn.update_entity("F-001", content_hash=hx("abc123"), title="Ignored")
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


def _ask_subject_gone(kg, iri: str) -> bool:
    from cataforge.domain.kg._ask import ask

    return not ask(kg.store, f"ASK {{ <{iri}> ?p ?o }}")


def _add_section_node(kg, config, doc_id: str = "prd", anchor: str = "§1 概览") -> str:
    from cataforge.domain.kg._quads import build_section_quads
    from cataforge.domain.kg.ingest.iri import document_iri, section_iri

    for q in build_section_quads(
        doc_id,
        anchor,
        anchor,
        "正文",
        "a" * 64,
        doc_id,
        config,
        document_iri_val=document_iri(doc_id, config.base_namespace),
    ):
        kg.store.add(q)
    return section_iri(doc_id, anchor, config.base_namespace)


def test_delete_section_by_relative_id_with_doc_prefix() -> None:
    kg, config, _project_iri = _make_kg()
    iri = _add_section_node(kg, config)

    with kg.transaction() as txn:
        txn.delete_entity("doc/prd/sec/§1 概览")

    assert _ask_subject_gone(kg, iri)


def test_delete_section_by_relative_id_without_doc_prefix() -> None:
    kg, config, _project_iri = _make_kg()
    iri = _add_section_node(kg, config)

    with kg.transaction() as txn:
        txn.delete_entity("prd/sec/§1 概览")

    assert _ask_subject_gone(kg, iri)


def test_delete_section_by_full_iri() -> None:
    kg, config, _project_iri = _make_kg()
    iri = _add_section_node(kg, config)

    with kg.transaction() as txn:
        txn.delete_entity(iri)

    assert _ask_subject_gone(kg, iri)


def test_delete_document_by_relative_id() -> None:
    from cataforge.domain.kg._quads import build_document_quads
    from cataforge.domain.kg.ingest.iri import document_iri

    kg, config, _project_iri = _make_kg()
    for q in build_document_quads("prd", "prd", "PRD", "prd", "b" * 64, config):
        kg.store.add(q)
    iri = document_iri("prd", config.base_namespace)

    with kg.transaction() as txn:
        txn.delete_entity("doc/prd")

    assert _ask_subject_gone(kg, iri)


def test_delete_flat_entity_by_full_iri() -> None:
    kg, config, _project_iri = _make_kg_with_entity()

    with kg.transaction() as txn:
        txn.delete_entity("https://cataforge.dev/instance/F-001")

    assert not kg.query.exists("F-001")


def test_delete_subordinate_by_scoped_id() -> None:
    from cataforge.domain.kg._quads import build_entity_quads
    from cataforge.domain.kg.ingest.iri import subordinate_entity_iri

    kg, config, project_iri = _make_kg_with_entity()
    for q in build_entity_quads(
        "AC-001",
        "AcceptanceCriteria",
        "登录验收",
        "prd",
        "AC-001 登录验收",
        "c" * 64,
        project_iri,
        config,
        parent_id="F-001",
    ):
        kg.store.add(q)

    with kg.transaction() as txn:
        txn.delete_entity("F-001/AC-001")

    iri = subordinate_entity_iri("F-001", "AC-001", config.base_namespace)
    assert _ask_subject_gone(kg, iri)
    assert kg.query.exists("F-001")


def test_delete_unknown_section_reports_resolved_form() -> None:
    kg, config, _project_iri = _make_kg()

    from cataforge.domain.kg import KGEntityNotFoundError

    with pytest.raises(KGEntityNotFoundError) as excinfo, kg.transaction() as txn:
        txn.delete_entity("doc/nope/sec/missing")

    message = str(excinfo.value)
    assert "not found" in message
    assert "section" in message
    assert "/doc/nope/sec/missing" in message


def test_delete_malformed_structural_id_raises_validation_error() -> None:
    kg, config, _project_iri = _make_kg()

    from cataforge.domain.kg import KGValidationError

    with pytest.raises(KGValidationError), kg.transaction() as txn:
        txn.delete_entity("doc/")


def test_delete_entity_without_cascade_rejects_incoming_edges() -> None:
    kg, config, project_iri = _make_kg_with_entity()

    with kg.transaction() as txn:
        txn.add_entity(
            entity_id="M-001",
            class_name="Module",
            title="Auth",
            source_doc="arch",
            source_section="M-001 Auth",
            content_hash=hx("mod1"),
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
            content_hash=hx("mod1"),
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
            content_hash=hx("mod1"),
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
            content_hash=hx("mod1"),
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
            content_hash=hx("mod1"),
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
            content_hash=hx("temp"),
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
                content_hash=hx(delay_name),
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
