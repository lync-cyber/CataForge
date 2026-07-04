"""Page / Task scalar-slot extraction via the standard entity_extract path."""

from __future__ import annotations

from pathlib import Path


def _parsed_doc(doc_id: str, doc_type: str, body: str):
    from cataforge.domain.kg.ingest.scan import (
        ParsedDoc,
        _code_block_char_ranges,
        heading_spans,
    )

    return ParsedDoc(
        doc_id=doc_id,
        doc_type=doc_type,
        file_path=Path(f"{doc_id}.md"),
        mtime=0.0,
        raw=body,
        body=body,
        body_offset=0,
        sections=heading_spans(body, 0),
        code_block_offsets=_code_block_char_ranges(body),
    )


# -- unit: extractor functions ------------------------------------------------


def test_page_extractor_pulls_route_and_layout() -> None:
    from cataforge.domain.kg.ingest.entity_extract import (
        ExtractedEntity,
        _extract_page_slots,
    )

    entity = ExtractedEntity(
        entity_id="P-001",
        class_name="Page",
        source_doc="ui-spec",
        source_section="P-001",
        content_hash="h",
        section_line_start=0,
        section_line_end=0,
        file_path=Path("x"),
        mtime=0.0,
    )
    _extract_page_slots(entity, "## P-001 Login\n\n- Route: /login\n- Layout: single-column\n")
    assert entity.extra_slots["cf:ui_route"] == "/login"
    assert entity.extra_slots["cf:layout_spec"] == "single-column"


def test_page_extractor_omits_absent_labels() -> None:
    from cataforge.domain.kg.ingest.entity_extract import (
        ExtractedEntity,
        _extract_page_slots,
    )

    entity = ExtractedEntity(
        entity_id="P-002",
        class_name="Page",
        source_doc="ui-spec",
        source_section="P-002",
        content_hash="h",
        section_line_start=0,
        section_line_end=0,
        file_path=Path("x"),
        mtime=0.0,
    )
    _extract_page_slots(entity, "## P-002 Bare\n\n- some unrelated bullet\n")
    assert entity.extra_slots == {}


def test_task_extractor_normalizes_status() -> None:
    from cataforge.domain.kg.ingest.entity_extract import (
        ExtractedEntity,
        _extract_task_slots,
    )

    entity = ExtractedEntity(
        entity_id="T-001",
        class_name="Task",
        source_doc="dev-plan",
        source_section="T-001",
        content_hash="h",
        section_line_start=0,
        section_line_end=0,
        file_path=Path("x"),
        mtime=0.0,
    )
    _extract_task_slots(entity, "## T-001 Build\n\n- Status: In Progress\n")
    assert entity.extra_slots["cf:task_status"] == "in_progress"


def test_task_extractor_drops_invalid_status() -> None:
    from cataforge.domain.kg.ingest.entity_extract import (
        ExtractedEntity,
        _extract_task_slots,
    )

    entity = ExtractedEntity(
        entity_id="T-002",
        class_name="Task",
        source_doc="dev-plan",
        source_section="T-002",
        content_hash="h",
        section_line_start=0,
        section_line_end=0,
        file_path=Path("x"),
        mtime=0.0,
    )
    _extract_task_slots(entity, "## T-002 Build\n\n- Status: almost-there\n")
    assert entity.extra_slots == {}


# -- integration: extract_entities over a parsed doc --------------------------


def test_extract_entities_enriches_page() -> None:
    from cataforge.domain.kg.ingest.entity_extract import extract_entities

    doc = _parsed_doc(
        "ui-spec",
        "ui-spec",
        "# UI Spec\n\n## P-001 Login Page\n\n- Route: /login\n- Layout: single-column\n",
    )
    page = next(e for e in extract_entities(doc) if e.class_name == "Page")
    assert page.extra_slots["cf:ui_route"] == "/login"
    assert page.extra_slots["cf:layout_spec"] == "single-column"


def test_extract_entities_enriches_task() -> None:
    from cataforge.domain.kg.ingest.entity_extract import extract_entities

    doc = _parsed_doc(
        "dev-plan",
        "dev-plan",
        "# Dev Plan\n\n## T-001 Build auth\n\n- Status: done\n",
    )
    task = next(e for e in extract_entities(doc) if e.class_name == "Task")
    assert task.extra_slots["cf:task_status"] == "done"


# -- quad level: single-valued scalars produce exactly one quad ---------------


def test_build_entity_quads_single_valued_scalar() -> None:
    from cataforge.domain.kg import KGConfig
    from cataforge.domain.kg._quads import build_entity_quads

    config = KGConfig(store_backend="memory")
    quads = build_entity_quads(
        "P-001",
        "Page",
        "Login Page",
        "ui-spec",
        "P-001",
        "abc123",
        "https://cataforge.dev/instance/proj-test",
        config,
        extra_slots={"cf:ui_route": "/login", "cf:layout_spec": "single-column"},
    )
    route_quads = [q for q in quads if "ui_route" in q.predicate.value]
    assert len(route_quads) == 1
    assert route_quads[0].object.value == "/login"
