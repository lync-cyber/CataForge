"""End-to-end ingest_markdown — frontmatter + headings + prose."""

from __future__ import annotations

import textwrap
from pathlib import Path

from cataforge.kg.ingest.markdown import (
    ID_PREFIX_MAP,
    ingest_markdown,
)


def _write(path: Path, body: str) -> Path:
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_document_node_emitted_for_valid_frontmatter(tmp_path: Path) -> None:
    md = _write(tmp_path / "prd.md", """\
        ---
        id: prd-x
        doc_type: prd
        ---
        # PRD-X

        Body.
        """)
    result = ingest_markdown(md, project_root=tmp_path)
    assert result.document is not None
    assert result.document.iri == "cfk:doc/prd-x"
    types = [t for t in result.triples if t.p == "rdf:type" and t.s == "cfk:doc/prd-x"]
    assert types and types[0].o == "cfk:Document"


def test_orphan_returns_empty_when_no_id(tmp_path: Path) -> None:
    md = _write(tmp_path / "no-fm.md", "# Just a heading\n")
    result = ingest_markdown(md, project_root=tmp_path)
    assert result.document is None
    assert result.items == []
    assert result.triples == []


def test_item_classification_by_id_prefix(tmp_path: Path) -> None:
    md = _write(tmp_path / "prd.md", """\
        ---
        id: prd-x
        ---
        # PRD-X

        ## F-001 用户登录
        Body for F-001.

        ## US-001 作为访客
        Body.

        ## NFR-001 响应延迟
        Body.
        """)
    result = ingest_markdown(md, project_root=tmp_path)
    item_classes = {it.display_id: it.item_class for it in result.items}
    assert item_classes == {
        "F-001":   "cfa:Feature",
        "US-001":  "cfa:UserStory",
        "NFR-001": "cfa:NFR",
    }


def test_release_semver_classified(tmp_path: Path) -> None:
    md = _write(tmp_path / "rel.md", """\
        ---
        id: release-notes
        ---
        # Releases

        ## v0.5.0 KG cutover
        Body.
        """)
    result = ingest_markdown(md, project_root=tmp_path)
    assert any(it.item_class == "cfa:Release" for it in result.items)


def test_section_number_prefix_stripped(tmp_path: Path) -> None:
    md = _write(tmp_path / "prd.md", """\
        ---
        id: prd-x
        ---
        # PRD-X

        ## 2.3 F-001 用户登录
        """)
    result = ingest_markdown(md, project_root=tmp_path)
    assert result.items and result.items[0].display_id == "F-001"


def test_unknown_id_prefix_skipped(tmp_path: Path) -> None:
    md = _write(tmp_path / "prd.md", """\
        ---
        id: prd-x
        ---
        # PRD-X

        ## ZZZ-001 unknown family
        """)
    result = ingest_markdown(md, project_root=tmp_path)
    assert result.items == []


def test_frontmatter_relation_resolved_to_item(tmp_path: Path) -> None:
    md = _write(tmp_path / "arch.md", """\
        ---
        id: arch-x
        realizes: F-001
        ---
        # Arch-X

        ## M-001 auth module
        """)
    result = ingest_markdown(
        md, project_root=tmp_path,
        known_item_iris={"F-001": "cfa:prd-x/F-001"},
    )
    triples = {(t.s, t.p, t.o) for t in result.triples}
    assert ("cfk:doc/arch-x", "cfa:realizes", "cfa:prd-x/F-001") in triples


def test_prose_ref_emits_references_triple(tmp_path: Path) -> None:
    md = _write(tmp_path / "prd.md", """\
        ---
        id: prd-x
        ---
        # PRD-X

        ## F-001 login
        Body.

        ## F-002 signup
        See also F-001 for context.
        """)
    result = ingest_markdown(md, project_root=tmp_path)
    triples = {(t.s, t.p, t.o) for t in result.triples}
    assert ("cfk:doc/prd-x", "cfa:references", "cfa:prd-x/F-001") in triples


def test_idempotent_on_repeat_ingest(tmp_path: Path) -> None:
    md = _write(tmp_path / "prd.md", """\
        ---
        id: prd-x
        ---
        # PRD-X

        ## F-001 login
        """)
    a = ingest_markdown(md, project_root=tmp_path).triples
    b = ingest_markdown(md, project_root=tmp_path).triples
    assert a == b


def test_content_hash_changes_on_body_edit(tmp_path: Path) -> None:
    md = _write(tmp_path / "prd.md", """\
        ---
        id: prd-x
        ---
        # PRD-X
        Original body.
        """)
    h1 = ingest_markdown(md, project_root=tmp_path).document
    assert h1 is not None
    _write(md, """\
        ---
        id: prd-x
        ---
        # PRD-X
        Mutated body.
        """)
    h2 = ingest_markdown(md, project_root=tmp_path).document
    assert h2 is not None
    assert h1.content_hash != h2.content_hash


def test_id_prefix_map_covers_design_table() -> None:
    # Regression guard: every prefix from design §1.8 ID-table must map
    # to a concrete cfa class. Add a check here when extending the table.
    for prefix in ("F", "US", "NFR", "M", "I", "T", "D", "R", "TC", "CU", "INC"):
        assert prefix in ID_PREFIX_MAP
