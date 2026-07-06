"""Atomicity tests for write_entities / _atomic_replace_entity (C2)."""

from __future__ import annotations

from pathlib import Path

import pytest


class _FailingStoreProxy:
    """Wraps a pyoxigraph Store and fails ``add`` after N successful calls.

    pyoxigraph 0.5.x makes ``Store.add`` a read-only attribute, so direct
    monkey-patching is rejected. This proxy delegates every other method
    to the underlying store while intercepting ``add`` to inject failure.
    """

    def __init__(self, store, fail_on_call: int) -> None:
        self._store = store
        self._fail_on_call = fail_on_call
        self.call_count = 0

    def add(self, quad) -> None:
        self.call_count += 1
        if self.call_count == self._fail_on_call:
            raise RuntimeError("injected failure")
        self._store.add(quad)

    def __getattr__(self, name):
        return getattr(self._store, name)


def _make_store_with_entity(entity_id: str = "F-001"):
    """Return (store, config, iri) with one entity pre-ingested."""
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg._quads import build_entity_quads
    from cataforge.domain.kg.ingest.iri import entity_iri

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    store = handle.raw
    project_iri = entity_iri("proj-default", config.base_namespace)
    for q in build_entity_quads(
        entity_id=entity_id,
        class_name="Feature",
        title="Original title",
        source_doc="prd",
        source_section=f"{entity_id} Original",
        content_hash="a" * 64,
        project_iri=project_iri,
        config=config,
    ):
        store.add(q)
    iri = entity_iri(entity_id, config.base_namespace)
    return store, config, iri


def test_atomic_replace_entity_happy_path() -> None:
    """_atomic_replace_entity replaces quads cleanly when no error occurs."""
    import pyoxigraph as ox

    from cataforge.domain.kg._quads import _slot_iri, build_entity_quads
    from cataforge.domain.kg.ingest.iri import entity_iri
    from cataforge.domain.kg.ingest.writer import _atomic_replace_entity

    store, config, iri = _make_store_with_entity("F-001")
    project_iri = entity_iri("proj-default", config.base_namespace)
    new_quads = build_entity_quads(
        entity_id="F-001",
        class_name="Feature",
        title="Updated title",
        source_doc="prd",
        source_section="F-001 Updated",
        content_hash="b" * 64,
        project_iri=project_iri,
        config=config,
    )
    namespace = config.ontology_namespace.rstrip("/") + "/"
    _atomic_replace_entity(store, iri, new_quads, namespace=namespace)

    title_pred = ox.NamedNode(_slot_iri("cf:title", namespace))
    subject = ox.NamedNode(iri)
    titles = [q.object.value for q in store.quads_for_pattern(subject, title_pred, None, None)]
    assert titles == ["Updated title"]


def test_atomic_replace_entity_rolls_back_on_failure() -> None:
    """Prior quads are restored when an exception interrupts the write."""
    from cataforge.domain.kg._quads import build_entity_quads, quads_for_subject
    from cataforge.domain.kg.ingest.iri import entity_iri
    from cataforge.domain.kg.ingest.writer import _atomic_replace_entity

    store, config, iri = _make_store_with_entity("F-001")
    prior_count = len(quads_for_subject(store, iri))

    project_iri = entity_iri("proj-default", config.base_namespace)
    new_quads = build_entity_quads(
        entity_id="F-001",
        class_name="Feature",
        title="Failing title",
        source_doc="prd",
        source_section="F-001 Fail",
        content_hash="c" * 64,
        project_iri=project_iri,
        config=config,
    )

    proxy = _FailingStoreProxy(store, fail_on_call=2)
    namespace = config.ontology_namespace.rstrip("/") + "/"
    with pytest.raises(RuntimeError, match="injected failure"):
        _atomic_replace_entity(proxy, iri, new_quads, namespace=namespace)

    restored = quads_for_subject(store, iri)
    assert len(restored) == prior_count, (
        f"Expected {prior_count} quads restored, got {len(restored)}"
    )


def test_write_entities_propagates_failure_keeping_prior_entities() -> None:
    """write_entities propagates a mid-batch failure; previously-written entities remain."""
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg._quads import quads_for_subject
    from cataforge.domain.kg.ingest.entity_extract import ExtractedEntity
    from cataforge.domain.kg.ingest.iri import entity_iri
    from cataforge.domain.kg.ingest.writer import write_entities

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    store = handle.raw
    project_iri = entity_iri("proj-default", config.base_namespace)

    entities = [
        ExtractedEntity(
            entity_id=f"F-{i:03d}",
            class_name="Feature",
            source_doc="prd",
            source_section=f"F-{i:03d} Test",
            content_hash=("d" * 63) + f"{i:01x}",
            section_line_start=0,
            section_line_end=1,
            file_path=Path("dummy.md"),
            mtime=0.0,
        )
        for i in range(1, 5)
    ]

    # Each entity writes ~8 quads. Fail mid-3rd-entity so F-001 + F-002 land.
    proxy = _FailingStoreProxy(store, fail_on_call=20)
    with pytest.raises(RuntimeError, match="injected failure"):
        write_entities(proxy, entities, project_iri, config)

    f001_iri = entity_iri("F-001", config.base_namespace)
    assert len(quads_for_subject(store, f001_iri)) > 0, "F-001 quads should remain"
