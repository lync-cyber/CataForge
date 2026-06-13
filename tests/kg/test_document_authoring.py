"""Document-structure authoring: parse helper, add_document, add_section order."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _make_kg():
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.ingest.writer import write_project

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    project_iri = write_project(handle.raw, "proj-test", "Test", "waterfall", config)
    return KnowledgeGraph(handle.raw, config), config, project_iri


def _ns(config) -> str:
    return config.ontology_namespace.rstrip("/") + "/"


# ---- parse_doc_text / scan_business_docs equivalence ------------------------


def test_parse_doc_text_matches_scan() -> None:
    from cataforge.domain.kg.ingest.scan import parse_doc_text, scan_business_docs

    docs = scan_business_docs(FIXTURE_ROOT / "waterfall", ["prd"])
    assert len(docs) == 1
    scanned = docs[0]

    raw = scanned.file_path.read_text()
    helper = parse_doc_text(
        raw,
        doc_type="prd",
        file_name=scanned.file_path.name,
        source_path=scanned.source_path,
        mtime=scanned.mtime,
        file_path=scanned.file_path,
    )
    assert helper.doc_id == scanned.doc_id
    assert helper.doc_type == scanned.doc_type
    assert helper.body == scanned.body
    assert helper.body_offset == scanned.body_offset
    assert helper.frontmatter == scanned.frontmatter
    assert helper.source_path == scanned.source_path
    assert [(s.line_start, s.line_end, s.level, s.title) for s in helper.sections] == [
        (s.line_start, s.line_end, s.level, s.title) for s in scanned.sections
    ]
    assert helper.code_block_offsets == scanned.code_block_offsets


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_parse_doc_text_marks_frontmatter_error() -> None:
    from cataforge.domain.kg.ingest.frontmatter import _PARSE_ERROR_KEY
    from cataforge.domain.kg.ingest.scan import parse_doc_text

    bad = "---\nid: [unclosed\n---\n# body\n"
    doc = parse_doc_text(
        bad, doc_type="prd", file_name="prd.md", source_path="docs/prd/prd.md", mtime=0.0
    )
    assert _PARSE_ERROR_KEY in doc.frontmatter


# ---- add_document idempotency -----------------------------------------------


def _document(doc_id: str = "prd", content_hash: str = "a" * 64):
    from cataforge.domain.kg.ingest.structure_extract import ExtractedDocument

    return ExtractedDocument(
        doc_id=doc_id,
        doc_type="prd",
        title="PRD",
        source_doc=doc_id,
        content_hash=content_hash,
        section_anchors=["§1"],
        version="0.1.0",
        status="draft",
        frontmatter_raw="---\nid: prd\ndoc_type: prd\n---\n",
        preamble_body="# PRD",
        source_path="docs/prd/prd.md",
    )


def test_add_document_creates_node() -> None:
    kg, config, _pi = _make_kg()
    with kg.transaction() as txn:
        iri = txn.add_document(_document())
    assert iri.endswith("/doc/prd")
    ns = _ns(config)
    rows = list(
        kg.store.query(
            f"PREFIX cf: <{ns}> SELECT ?fm ?st ?ver WHERE {{ "
            f"<{iri}> a cf:Document ; cf:frontmatter_raw ?fm ; cf:status ?st ; cf:version ?ver }}"
        )
    )
    assert rows
    assert rows[0]["st"].value == "draft"
    assert rows[0]["ver"].value == "0.1.0"


def test_add_document_idempotent_on_same_hash() -> None:
    kg, _config, _pi = _make_kg()
    with kg.transaction() as txn:
        txn.add_document(_document())
    with kg.transaction() as txn:
        txn.add_document(_document())
        assert txn.pending_inserts == 0
        assert txn.pending_deletes == 0


# ---- add_section position fidelity ------------------------------------------


def test_add_section_update_preserves_position() -> None:
    kg, config, _pi = _make_kg()
    with kg.transaction() as txn:
        txn.add_document(_document())
        txn.add_section("prd", "A", "## A\nfirst", "1" * 64, position=0, level=2)
        txn.add_section("prd", "B", "## B\nfirst", "2" * 64, position=1, level=2)

    # Update section B's body without giving a position: it must keep position 1.
    with kg.transaction() as txn:
        txn.add_section("prd", "B", "## B\nupdated body", "3" * 64)

    ns = _ns(config)
    rows = list(
        kg.store.query(
            f"PREFIX cf: <{ns}> SELECT ?anchor ?pos ?level WHERE {{ "
            '?s a cf:Section ; cf:source_doc "prd" ; cf:section_anchor ?anchor ; '
            "cf:position ?pos ; cf:section_level ?level } ORDER BY ?anchor"
        )
    )
    by_anchor = {r["anchor"].value: (r["pos"].value, r["level"].value) for r in rows}
    assert by_anchor["A"] == ("000000", "2")
    assert by_anchor["B"] == ("000001", "2")


def test_add_section_new_appends_max_plus_one() -> None:
    kg, config, _pi = _make_kg()
    with kg.transaction() as txn:
        txn.add_document(_document())
        txn.add_section("prd", "A", "## A\nbody", "1" * 64, position=0, level=2)
        txn.add_section("prd", "B", "## B\nbody", "2" * 64, position=1, level=2)

    # A new section without an explicit position appends after the last one.
    with kg.transaction() as txn:
        txn.add_section("prd", "C", "## C\nbody", "3" * 64)

    ns = _ns(config)
    rows = list(
        kg.store.query(
            f"PREFIX cf: <{ns}> SELECT ?pos WHERE {{ "
            '?s a cf:Section ; cf:section_anchor "C" ; cf:position ?pos }'
        )
    )
    assert rows and rows[0]["pos"].value == "000002"


def test_add_section_first_section_defaults_position_zero() -> None:
    kg, config, _pi = _make_kg()
    with kg.transaction() as txn:
        txn.add_document(_document())
        txn.add_section("prd", "Only", "## Only\nbody", "1" * 64)
    ns = _ns(config)
    rows = list(
        kg.store.query(
            f"PREFIX cf: <{ns}> SELECT ?pos WHERE {{ "
            '?s a cf:Section ; cf:section_anchor "Only" ; cf:position ?pos }'
        )
    )
    assert rows and rows[0]["pos"].value == "000000"


def test_add_section_explicit_level_recorded() -> None:
    kg, config, _pi = _make_kg()
    with kg.transaction() as txn:
        txn.add_document(_document())
        txn.add_section("prd", "Deep", "#### Deep\nbody", "1" * 64, level=4)
    ns = _ns(config)
    rows = list(
        kg.store.query(
            f"PREFIX cf: <{ns}> SELECT ?level WHERE {{ "
            '?s a cf:Section ; cf:section_anchor "Deep" ; cf:section_level ?level }'
        )
    )
    assert rows and rows[0]["level"].value == "4"


@pytest.mark.parametrize("variant", ["waterfall", "agile"])
def test_ingest_unchanged_after_refactor(variant: str) -> None:
    """Re-ingesting an unchanged source writes zero new structural quads."""
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, FIXTURE_ROOT / variant, config)
    second, _e, _r = run_migration(handle.raw, FIXTURE_ROOT / variant, config)
    assert second.structure_stats.sections_written == 0
    assert second.structure_stats.documents_written == 0
