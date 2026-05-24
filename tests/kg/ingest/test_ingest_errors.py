"""Error and edge-case tests for cataforge.kg.ingest.markdown."""

from __future__ import annotations

import textwrap
from pathlib import Path

from cataforge.kg.ingest.markdown import ingest_markdown


def _write(path: Path, body: str) -> Path:
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# (a) Duplicate display_id within a single document
# ---------------------------------------------------------------------------


def test_duplicate_item_id_within_doc_is_deduplicated(tmp_path: Path) -> None:
    """The same display_id heading appearing twice must yield exactly one item,
    and the generated triples must contain no duplicate subject IRIs for that id."""
    md = _write(tmp_path / "prd.md", """\
        ---
        id: prd-dup
        ---
        # PRD-DUP

        ## F-001 First occurrence
        Body.

        ## F-001 Second occurrence — duplicate
        Body.
        """)
    result = ingest_markdown(md, project_root=tmp_path)

    assert result.document is not None
    f001_items = [it for it in result.items if it.display_id == "F-001"]
    assert len(f001_items) == 1, (
        f"Expected exactly 1 F-001 item after deduplication, got {len(f001_items)}"
    )


def test_duplicate_item_id_does_not_produce_duplicate_triples(tmp_path: Path) -> None:
    md = _write(tmp_path / "prd.md", """\
        ---
        id: prd-dup2
        ---
        # PRD-DUP2

        ## F-002 First
        Body.

        ## F-002 Second
        Body.
        """)
    result = ingest_markdown(md, project_root=tmp_path)

    f002_type_triples = [
        t for t in result.triples
        if t.s.endswith("F-002") and t.p == "rdf:type"
    ]
    assert len(f002_type_triples) == 1, (
        f"Expected exactly 1 rdf:type triple for F-002, got {len(f002_type_triples)}"
    )


# ---------------------------------------------------------------------------
# (b) Malformed YAML frontmatter → treated as orphan (document=None)
# ---------------------------------------------------------------------------


def test_malformed_yaml_frontmatter_returns_orphan(tmp_path: Path) -> None:
    """A file whose YAML frontmatter cannot be parsed must be returned as an
    orphan — document=None, empty triples — rather than raising."""
    md = tmp_path / "bad-fm.md"
    # The double-colon is a YAML error: `id: : ` makes safe_load fail
    md.write_text("---\nid: : malformed\n---\n# Body\n", encoding="utf-8")

    result = ingest_markdown(md, project_root=tmp_path)

    assert result.document is None, (
        "Malformed YAML must produce an orphan result (document=None)"
    )
    assert result.triples == []
    assert result.items == []


def test_malformed_yaml_does_not_raise(tmp_path: Path) -> None:
    md = tmp_path / "bad-fm2.md"
    md.write_text("---\n: : : : :\n---\n# Body\n", encoding="utf-8")

    # Must not raise any exception
    result = ingest_markdown(md, project_root=tmp_path)
    assert result.triples == []


# ---------------------------------------------------------------------------
# (c) Deps referencing a nonexistent doc_id → triple is dropped (no crash)
# ---------------------------------------------------------------------------


def test_unresolved_dep_is_silently_dropped(tmp_path: Path) -> None:
    """A frontmatter deps entry pointing to an unknown doc_id must not produce
    a triple — unresolved references are dropped, not surfaced as exceptions."""
    md = _write(tmp_path / "arch.md", """\
        ---
        id: arch
        deps: [F-999-nonexistent]
        ---
        # Architecture
        Body.
        """)
    result = ingest_markdown(md, project_root=tmp_path)

    assert result.document is not None
    dep_triples = [t for t in result.triples if t.p == "cfa:dependsOn"]
    assert dep_triples == [], (
        "Unresolved deps must produce no cfa:dependsOn triple"
    )


def test_unresolved_dep_with_known_item_iris_resolves(tmp_path: Path) -> None:
    """When a dep IS present in known_item_iris, the triple must be emitted."""
    md = _write(tmp_path / "arch.md", """\
        ---
        id: arch
        deps: [F-001]
        ---
        # Architecture
        Body.
        """)
    result = ingest_markdown(
        md,
        project_root=tmp_path,
        known_item_iris={"F-001": "cfa:prd/F-001"},
    )

    assert result.document is not None
    dep_triples = [t for t in result.triples if t.p == "cfa:dependsOn"]
    assert any(t.o == "cfa:prd/F-001" for t in dep_triples), (
        "Resolved dep must produce a cfa:dependsOn triple pointing to the known IRI"
    )


# ---------------------------------------------------------------------------
# (d) Missing id field → orphan (no crash, empty result)
# ---------------------------------------------------------------------------


def test_missing_id_field_returns_orphan(tmp_path: Path) -> None:
    md = _write(tmp_path / "no-id.md", """\
        ---
        doc_type: prd
        ---
        # No ID
        Body.
        """)
    result = ingest_markdown(md, project_root=tmp_path)
    assert result.document is None
    assert result.triples == []
    assert result.items == []


# ---------------------------------------------------------------------------
# (e) Template placeholder in id → treated as orphan
# ---------------------------------------------------------------------------


def test_template_placeholder_id_is_orphan(tmp_path: Path) -> None:
    md = _write(tmp_path / "tpl.md", """\
        ---
        id: "{doc_id_placeholder}"
        ---
        # Template
        Body.
        """)
    result = ingest_markdown(md, project_root=tmp_path)
    assert result.document is None
