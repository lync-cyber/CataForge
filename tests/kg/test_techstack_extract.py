"""Tests for TechStack entity extraction via the standard entity_extract path."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _parse_arch(variant: str = "waterfall"):
    from cataforge.domain.kg.ingest.scan import scan_business_docs

    docs = scan_business_docs(FIXTURE_ROOT / variant, ["arch"])
    assert len(docs) == 1
    return docs[0]


def _open_memory_store():
    from cataforge.domain.kg import KGConfig, init_store

    config = KGConfig(store_backend="memory")
    return init_store(config, force=True), config


# -- unit tests: TechStack extracted via standard extract_entities -----------


def test_extract_entities_finds_techstack() -> None:
    from cataforge.domain.kg.ingest.entity_extract import extract_entities

    doc = _parse_arch("waterfall")
    entities = extract_entities(doc)
    ts = [e for e in entities if e.class_name == "TechStack"]

    assert len(ts) == 1
    assert ts[0].entity_id == "TS-001"
    assert ts[0].source_doc == "arch"


def test_techstack_narrative_body_in_extra_slots() -> None:
    from cataforge.domain.kg.ingest.entity_extract import extract_entities

    entities = extract_entities(_parse_arch())
    ts = next(e for e in entities if e.class_name == "TechStack")
    body = ts.extra_slots.get("cf:narrative_body", "")
    assert "Python 3.12" in body


def test_techstack_stack_layers_in_extra_slots() -> None:
    from cataforge.domain.kg.ingest.entity_extract import extract_entities

    entities = extract_entities(_parse_arch())
    ts = next(e for e in entities if e.class_name == "TechStack")
    layers = ts.extra_slots.get("cf:stack_layers", [])
    assert isinstance(layers, list)
    assert len(layers) == 3
    assert any("Python" in layer for layer in layers)
    assert any("JWT" in layer for layer in layers)


def test_non_techstack_entities_have_empty_extra_slots() -> None:
    from cataforge.domain.kg.ingest.entity_extract import extract_entities

    entities = extract_entities(_parse_arch())
    non_ts = [e for e in entities if e.class_name != "TechStack"]
    assert all(e.extra_slots == {} for e in non_ts)


# -- integration: TechStack in the full migration pipeline -------------------


@pytest.mark.parametrize("variant", ("waterfall", "agile"))
def test_migration_includes_techstack(variant: str) -> None:
    from cataforge.domain.kg.ingest import run_migration

    handle, config = _open_memory_store()
    root = FIXTURE_ROOT / variant
    stats, entities, _ = run_migration(handle.raw, root, config)

    ts_entities = [e for e in entities if e.class_name == "TechStack"]
    assert len(ts_entities) == 1
    assert ts_entities[0].entity_id == "TS-001"

    rows = list(
        handle.raw.query(
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "SELECT ?eid WHERE { ?s a cf:TechStack ; cf:entity_id ?eid }"
        )
    )
    assert len(rows) == 1
    assert rows[0]["eid"].value == "TS-001"


@pytest.mark.parametrize("variant", ("waterfall", "agile"))
def test_techstack_narrative_body_in_store(variant: str) -> None:
    from cataforge.domain.kg.ingest import run_migration

    handle, config = _open_memory_store()
    run_migration(handle.raw, FIXTURE_ROOT / variant, config)

    rows = list(
        handle.raw.query(
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "SELECT ?body WHERE { ?s a cf:TechStack ; cf:narrative_body ?body }"
        )
    )
    assert len(rows) == 1
    assert "Python 3.12" in rows[0]["body"].value


@pytest.mark.parametrize("variant", ("waterfall", "agile"))
def test_techstack_stack_layers_in_store(variant: str) -> None:
    from cataforge.domain.kg.ingest import run_migration

    handle, config = _open_memory_store()
    run_migration(handle.raw, FIXTURE_ROOT / variant, config)

    rows = list(
        handle.raw.query(
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "SELECT ?layer WHERE { ?s a cf:TechStack ; cf:stack_layers ?layer }"
        )
    )
    layer_values = {r["layer"].value for r in rows}
    assert len(layer_values) == 3


# -- _quads.py: multivalued extra_slots --------------------------------------


def test_build_entity_quads_multivalued_extra_slots() -> None:
    from cataforge.domain.kg import KGConfig
    from cataforge.domain.kg._quads import build_entity_quads

    config = KGConfig(store_backend="memory")
    quads = build_entity_quads(
        "TS-001",
        "TechStack",
        "Demo Stack",
        "arch",
        "§1.4",
        "abc123",
        "https://cataforge.dev/instance/proj-test",
        config,
        extra_slots={
            "cf:narrative_body": "Some text",
            "cf:stack_layers": ["layer-a", "layer-b", "layer-c"],
        },
    )
    layer_quads = [q for q in quads if "stack_layers" in q.predicate.value]
    assert len(layer_quads) == 3
    layer_values = {q.object.value for q in layer_quads}
    assert layer_values == {"layer-a", "layer-b", "layer-c"}

    body_quads = [q for q in quads if "narrative_body" in q.predicate.value]
    assert len(body_quads) == 1
    assert body_quads[0].object.value == "Some text"
