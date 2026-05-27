"""Tests for TechStack entity extraction from arch documents."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pyoxigraph_installed = importlib.util.find_spec("pyoxigraph") is not None
linkml_runtime_installed = importlib.util.find_spec("linkml_runtime") is not None

pytestmark = pytest.mark.skipif(
    not (pyoxigraph_installed and linkml_runtime_installed),
    reason="kg extra not installed (pyoxigraph + linkml-runtime)",
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _parse_arch(variant: str = "waterfall"):
    from cataforge.kg.ingest.scan import scan_business_docs

    docs = scan_business_docs(FIXTURE_ROOT / variant, ["arch"])
    assert len(docs) == 1
    return docs[0]


def _open_memory_store():
    from cataforge.kg import KGConfig
    from cataforge.kg.store import init_store

    config = KGConfig(store_backend="memory")
    return init_store(config, force=True), config


# -- unit tests for extract_techstack ----------------------------------------

def test_extract_techstack_from_section_14() -> None:
    from cataforge.kg.ingest.techstack_extract import extract_techstack

    doc = _parse_arch("waterfall")
    ts = extract_techstack(doc)

    assert ts is not None
    assert ts.entity_id == "tech-stack-arch"
    assert ts.class_name == "TechStack"
    assert ts.source_doc == "arch"
    assert "技术栈" in ts.source_section


def test_narrative_body_populated() -> None:
    from cataforge.kg.ingest.techstack_extract import extract_techstack

    ts = extract_techstack(_parse_arch())
    assert ts is not None
    body = ts.extra_slots.get("cf:narrative_body", "")
    assert "Python 3.12" in body


def test_stack_layers_parsed() -> None:
    from cataforge.kg.ingest.techstack_extract import extract_techstack

    ts = extract_techstack(_parse_arch())
    assert ts is not None
    layers = ts.extra_slots.get("cf:stack_layers", [])
    assert isinstance(layers, list)
    assert len(layers) == 3
    assert any("Python" in layer for layer in layers)
    assert any("JWT" in layer for layer in layers)


def test_no_techstack_when_absent(tmp_path: Path) -> None:
    from cataforge.kg.ingest.scan import ParsedDoc
    from cataforge.kg.ingest.techstack_extract import extract_techstack

    doc = ParsedDoc(
        doc_id="arch",
        doc_type="arch",
        file_path=tmp_path / "arch.md",
        mtime=0.0,
        raw="# Architecture\n\n## §2 Modules\n\nSome content.\n",
        body="## §2 Modules\n\nSome content.\n",
        body_offset=2,
        sections=[],
    )
    assert extract_techstack(doc) is None


def test_non_arch_doc_returns_none(tmp_path: Path) -> None:
    from cataforge.kg.ingest.scan import HeadingSpan, ParsedDoc
    from cataforge.kg.ingest.techstack_extract import extract_techstack

    doc = ParsedDoc(
        doc_id="prd",
        doc_type="prd",
        file_path=tmp_path / "prd.md",
        mtime=0.0,
        raw="# PRD\n\n### §1.4 技术栈\n\n- item\n",
        body="### §1.4 技术栈\n\n- item\n",
        body_offset=2,
        sections=[HeadingSpan(line_start=2, line_end=5, level=3, title="§1.4 技术栈")],
    )
    assert extract_techstack(doc) is None


# -- integration: TechStack in the full migration pipeline -------------------

@pytest.mark.parametrize("variant", ("waterfall", "agile"))
def test_migration_includes_techstack(variant: str) -> None:
    from cataforge.kg.ingest import run_migration

    handle, config = _open_memory_store()
    root = FIXTURE_ROOT / variant
    stats, entities, _ = run_migration(handle.raw, root, config)

    ts_entities = [e for e in entities if e.class_name == "TechStack"]
    assert len(ts_entities) == 1
    assert ts_entities[0].entity_id == "tech-stack-arch"

    rows = list(
        handle.raw.query(
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "SELECT ?eid WHERE { ?s a cf:TechStack ; cf:entity_id ?eid }"
        )
    )
    assert len(rows) == 1
    assert rows[0]["eid"].value == "tech-stack-arch"


@pytest.mark.parametrize("variant", ("waterfall", "agile"))
def test_techstack_narrative_body_in_store(variant: str) -> None:
    from cataforge.kg.ingest import run_migration

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
    from cataforge.kg.ingest import run_migration

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
    from cataforge.kg import KGConfig
    from cataforge.kg._quads import build_entity_quads

    config = KGConfig(store_backend="memory")
    quads = build_entity_quads(
        "tech-stack-demo",
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
    layer_quads = [
        q for q in quads
        if "stack_layers" in q.predicate.value
    ]
    assert len(layer_quads) == 3
    layer_values = {q.object.value for q in layer_quads}
    assert layer_values == {"layer-a", "layer-b", "layer-c"}

    body_quads = [
        q for q in quads
        if "narrative_body" in q.predicate.value
    ]
    assert len(body_quads) == 1
    assert body_quads[0].object.value == "Some text"
