"""Whole-document KG → Markdown reconstruction and round-trip idempotency."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _connect_kg_first(project_root: Path):
    """Open a kg-first store seeded by ingesting `project_root`'s docs."""
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, project_root, config)
    return handle, config


def _normalize(text: str) -> str:
    """Collapse trailing blank lines per inter-section join and end-of-file.

    Sections are joined by exactly one blank line; the file ends with a
    single newline. This matches the reconstruction's canonical form so a
    semantic-equivalence comparison ignores incidental blank-line runs.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip() == "":
            blank_run += 1
            if blank_run > 1:
                continue
            out.append("")
        else:
            blank_run = 0
            out.append(line)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


# --- reconstruction: whole document from the graph ---------------------------


def test_compile_documents_rebuilds_each_source_file(tmp_path: Path) -> None:
    from cataforge.domain.kg.export.document_pipeline import compile_documents

    handle, _config = _connect_kg_first(FIXTURE_ROOT / "waterfall")
    out = tmp_path / "out"
    result = compile_documents(handle.raw, out)
    assert not result.errors, result.errors

    for rel in ("prd/prd-vertical-slice.md", "arch/arch-vertical-slice.md"):
        rebuilt = (out / rel).read_text(encoding="utf-8")
        source = (FIXTURE_ROOT / "waterfall" / "docs" / rel).read_text(encoding="utf-8")
        assert _normalize(rebuilt) == _normalize(source), rel


def test_reconstruction_preserves_frontmatter_fields(tmp_path: Path) -> None:
    from cataforge.domain.kg.export.document_pipeline import compile_documents

    src_root = tmp_path / "proj"
    prd_dir = src_root / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    (src_root / ".cataforge").mkdir()
    (src_root / ".cataforge" / "framework.json").write_text(_FRAMEWORK_JSON, encoding="utf-8")
    prd_text = (
        "---\n"
        "doc_id: prd\n"
        "doc_type: prd\n"
        "author: product-manager\n"
        "status: approved\n"
        "deps: []\n"
        "version: 1.2.0\n"
        "---\n"
        "\n"
        "# Heading that differs from frontmatter title\n"
        "\n"
        "Preamble prose before any section.\n"
        "\n"
        "## §1 Scope\n"
        "\n"
        "Scope body text.\n"
    )
    (prd_dir / "prd-proj.md").write_text(prd_text, encoding="utf-8")

    handle, _config = _connect_kg_first(src_root)
    out = tmp_path / "out"
    compile_documents(handle.raw, out)
    rebuilt = (out / "prd" / "prd-proj.md").read_text(encoding="utf-8")
    assert "author: product-manager" in rebuilt
    assert "status: approved" in rebuilt
    assert "version: 1.2.0" in rebuilt
    # The H1 line is preamble content, not the frontmatter title.
    assert "# Heading that differs from frontmatter title" in rebuilt
    assert "Preamble prose before any section." in rebuilt


def test_reconstruction_preserves_document_order_not_lexical(tmp_path: Path) -> None:
    from cataforge.domain.kg.export.document_pipeline import compile_documents

    src_root = tmp_path / "proj"
    prd_dir = src_root / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    (src_root / ".cataforge").mkdir()
    (src_root / ".cataforge" / "framework.json").write_text(_FRAMEWORK_JSON, encoding="utf-8")
    headings = [f"## §{i} Section {i}" for i in range(1, 13)]
    bodies = [f"Body of section {i}." for i in range(1, 13)]
    parts = ["---\ndoc_id: prd\ndoc_type: prd\n---\n", "# Doc\n"]
    for h, b in zip(headings, bodies, strict=True):
        parts.append(f"\n{h}\n\n{b}\n")
    prd_text = "".join(parts)
    (prd_dir / "prd-proj.md").write_text(prd_text, encoding="utf-8")

    handle, _config = _connect_kg_first(src_root)
    out = tmp_path / "out"
    compile_documents(handle.raw, out)
    rebuilt = (out / "prd" / "prd-proj.md").read_text(encoding="utf-8")

    positions = [rebuilt.index(f"Section {i}") for i in range(1, 13)]
    assert positions == sorted(positions), "sections must appear in document order"
    # Lexical sort would place "§10" before "§2"; document order must not.
    assert rebuilt.index("Section 2") < rebuilt.index("Section 10")


# --- round-trip idempotency --------------------------------------------------


def _sha_map(directory: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(directory.rglob("*.md")):
        rel = str(path.relative_to(directory)).replace("\\", "/")
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def test_finalize_ingest_finalize_is_byte_idempotent(tmp_path: Path) -> None:
    from cataforge.application.context import write as ctx_write

    src_root = _copy_fixture(FIXTURE_ROOT / "waterfall", tmp_path)
    _init_on_disk_store(src_root)
    _set_graph_authoring(src_root)

    ctx_write.ingest(str(src_root))
    ctx_write.finalize(str(src_root))
    first = _sha_map(src_root / "docs")

    ctx_write.ingest(str(src_root))
    ctx_write.finalize(str(src_root))
    second = _sha_map(src_root / "docs")

    assert first == second, "finalize → ingest → finalize must be byte-identical"


def test_byte_exact_on_normalized_source(tmp_path: Path) -> None:
    """A source already in canonical form rebuilds byte-for-byte."""
    from cataforge.domain.kg.export.document_pipeline import compile_documents

    src_root = tmp_path / "proj"
    prd_dir = src_root / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    (src_root / ".cataforge").mkdir()
    (src_root / ".cataforge" / "framework.json").write_text(_FRAMEWORK_JSON, encoding="utf-8")
    prd_text = (
        "---\n"
        "doc_id: prd\n"
        "doc_type: prd\n"
        "---\n"
        "\n"
        "# PRD\n"
        "\n"
        "Intro line.\n"
        "\n"
        "## §1 Scope\n"
        "\n"
        "Scope body.\n"
        "\n"
        "## §2 Detail\n"
        "\n"
        "Detail body.\n"
    )
    (prd_dir / "prd-proj.md").write_text(prd_text, encoding="utf-8")

    handle, _config = _connect_kg_first(src_root)
    out = tmp_path / "out"
    compile_documents(handle.raw, out)
    rebuilt = (out / "prd" / "prd-proj.md").read_text(encoding="utf-8")
    assert rebuilt == prd_text


# --- entity-less authored documents ------------------------------------------


_ALL_DOC_TYPES = ("prd", "arch", "ui-spec", "dev-plan", "test-report", "deploy-spec")

_ALL_TYPES_FRAMEWORK_JSON = """{
  "docs": {"doc_types": {"prd": "prd", "arch": "arch", "ui-spec": "ui-spec",
    "dev-plan": "dev-plan", "test-report": "test-report", "deploy-spec": "deploy-spec"}},
  "context": {"strategy": "kg-first", "authoring": "graph"},
  "kg": {"project_id": "proj-test", "title": "Test", "process_model": "waterfall"}
}
"""


def _prose_doc(doc_type: str) -> str:
    return (
        f"---\nid: {doc_type}\ndoc_type: {doc_type}\nstatus: draft\n---\n\n"
        f"# {doc_type} title\n\nPreamble prose for {doc_type}.\n\n"
        f"## §1 概览\n\nOverview prose for {doc_type}.\n\n"
        f"## §2 详情\n\nDetail prose for {doc_type}.\n"
    )


_REPRESENTATIVE_ENTITIES: dict[str, tuple[tuple[str, str], ...]] = {
    "prd": (("F-001", "Login"),),
    "arch": (("M-001", "Auth module"),),
    "ui-spec": (("P-001", "Login page"), ("UC-001", "Login form")),
    "dev-plan": (("T-001", "Implement auth"),),
    "test-report": (("TC-001", "Login smoke"),),
    "deploy-spec": (
        ("ENV-001", "Production"),
        ("REL-001", "Release v1"),
        ("DP-001", "Deploy v1"),
        ("PL-001", "CI pipeline"),
    ),
}


def _entity_doc(doc_type: str, entities: tuple[tuple[str, str], ...]) -> str:
    head = (
        f"---\nid: {doc_type}\ndoc_type: {doc_type}\nstatus: draft\n---\n\n"
        f"# {doc_type} title\n\nPreamble.\n\n## §2 Entities\n"
    )
    blocks = [
        f"\n### §2.{i} {eid} {title}\n\nBody for {eid}.\n"
        for i, (eid, title) in enumerate(entities, 1)
    ]
    return head + "".join(blocks)


def test_per_entity_cards_render_for_all_doc_types(tmp_path: Path) -> None:
    """Every doc_type's entities render a per-entity card on the read surface.

    Bespoke-templated classes (Feature/Module/Page/UIComponent/Task/TestCase)
    and generic-fallback classes (Deployment/Pipeline/Environment/Release)
    must all surface a card so no doc_type is silently prd-only.
    """
    from cataforge.domain.kg.export import compile_to_markdown

    src_root = tmp_path / "proj"
    (src_root / ".cataforge").mkdir(parents=True)
    (src_root / ".cataforge" / "framework.json").write_text(
        _ALL_TYPES_FRAMEWORK_JSON, encoding="utf-8"
    )
    for doc_type, entities in _REPRESENTATIVE_ENTITIES.items():
        doc_dir = src_root / "docs" / doc_type
        doc_dir.mkdir(parents=True)
        (doc_dir / f"{doc_type}-proj.md").write_text(
            _entity_doc(doc_type, entities), encoding="utf-8"
        )

    handle, _config = _connect_kg_first(src_root)
    out = tmp_path / "cards"
    result = compile_to_markdown(handle.raw, out)
    assert not result.errors, result.errors

    rendered = {p.name for p in out.rglob("*.md")}
    for doc_type, entities in _REPRESENTATIVE_ENTITIES.items():
        for entity_id, _title in entities:
            assert f"{entity_id}.md" in rendered, (
                f"{doc_type} entity {entity_id} must render a per-entity card"
            )


def test_finalize_exports_entityless_authored_documents(tmp_path: Path) -> None:
    """Authored Documents with zero business entities must still export.

    finalize must not mistake an entity-less graph for an empty (md-first)
    one and skip the kg-first export — that would silently drop authored
    structure for prose-only or early-draft documents of any doc_type.
    """
    from cataforge.application.context import write as ctx_write

    src_root = tmp_path / "proj"
    (src_root / ".cataforge").mkdir(parents=True)
    (src_root / ".cataforge" / "framework.json").write_text(
        _ALL_TYPES_FRAMEWORK_JSON, encoding="utf-8"
    )
    _init_on_disk_store(src_root)

    for doc_type in _ALL_DOC_TYPES:
        ctx_write.author_document(
            str(src_root),
            _prose_doc(doc_type),
            source_path=f"docs/{doc_type}/{doc_type}-proj.md",
        )

    ctx_write.finalize(str(src_root))

    for doc_type in _ALL_DOC_TYPES:
        exported = src_root / "docs" / doc_type / f"{doc_type}-proj.md"
        assert exported.is_file(), f"entity-less {doc_type} Document must be exported"
        assert exported.read_text(encoding="utf-8") == _prose_doc(doc_type), doc_type


# --- orphan fallback ---------------------------------------------------------


def test_orphan_entity_falls_back_to_per_entity_card(tmp_path: Path) -> None:
    from cataforge.domain.kg.export.document_pipeline import compile_documents

    handle, config = _connect_kg_first(FIXTURE_ROOT / "waterfall")
    # Author an entity directly into the graph with a source_doc that has no
    # Document node → it must export as a per-entity card.
    from cataforge.domain.kg.ingest.entity_extract import ExtractedEntity
    from cataforge.domain.kg.ingest.writer import write_entities, write_project

    orphan = ExtractedEntity(
        entity_id="F-900",
        class_name="Feature",
        source_doc="ghost-doc",
        source_section="F-900 Orphan",
        content_hash=hashlib.sha256(b"orphan").hexdigest(),
        section_line_start=0,
        section_line_end=1,
        file_path=Path("ghost-doc.md"),
        mtime=0.0,
    )
    project_iri = write_project(handle.raw, "proj-x", "X", "waterfall", config)
    write_entities(handle.raw, [orphan], project_iri, config)

    out = tmp_path / "out"
    result = compile_documents(handle.raw, out)
    assert (out / "prd" / "F-900.md").is_file(), "orphan must land as per-entity card"
    rendered = {p.name for p in out.rglob("*.md")}
    assert "F-900.md" in rendered
    assert any("F-900" in r for r in result.file_hashes), result.file_hashes


# --- split-volume reconstruction (multiple files, same doc_type) -------------


def test_split_volume_files_each_reconstructed(tmp_path: Path) -> None:
    from cataforge.domain.kg.export.document_pipeline import compile_documents

    src_root = tmp_path / "proj"
    prd_dir = src_root / "docs" / "prd"
    prd_dir.mkdir(parents=True)
    (src_root / ".cataforge").mkdir()
    (src_root / ".cataforge" / "framework.json").write_text(_FRAMEWORK_JSON, encoding="utf-8")
    vol_a = (
        "---\ndoc_id: prd-vol-a\ndoc_type: prd\n---\n\n# Volume A\n\n## §1 Alpha\n\nAlpha body.\n"
    )
    vol_b = "---\ndoc_id: prd-vol-b\ndoc_type: prd\n---\n\n# Volume B\n\n## §1 Beta\n\nBeta body.\n"
    (prd_dir / "prd-vol-a.md").write_text(vol_a, encoding="utf-8")
    (prd_dir / "prd-vol-b.md").write_text(vol_b, encoding="utf-8")

    handle, _config = _connect_kg_first(src_root)
    out = tmp_path / "out"
    compile_documents(handle.raw, out)
    assert (out / "prd" / "prd-vol-a.md").read_text(encoding="utf-8") == vol_a
    assert (out / "prd" / "prd-vol-b.md").read_text(encoding="utf-8") == vol_b


# --- finalize routing --------------------------------------------------------


def test_finalize_uses_whole_doc_export(tmp_path: Path) -> None:
    from cataforge.application.context import write as ctx_write

    src_root = _copy_fixture(FIXTURE_ROOT / "waterfall", tmp_path)
    _init_on_disk_store(src_root)
    _set_graph_authoring(src_root)
    ctx_write.ingest(str(src_root))
    result = ctx_write.finalize(str(src_root))
    # Whole-doc export writes back to source paths, not per-entity F-xxx.md files.
    prd = (src_root / "docs" / "prd" / "prd-vertical-slice.md").read_text(encoding="utf-8")
    assert "F-001" in prd and "## §" in prd
    # No spurious per-entity card for an entity that belongs to a document.
    assert not (src_root / "docs" / "prd" / "F-001.md").is_file()
    assert result is not None


_FRAMEWORK_JSON = """{
  "docs": {"doc_types": {"prd": "prd", "arch": "arch", "test-report": "test-report"}},
  "context": {"strategy": "kg-first"},
  "kg": {
    "project_id": "proj-test",
    "title": "Test",
    "process_model": "waterfall"
  }
}
"""


def _copy_fixture(fixture_root: Path, dest_parent: Path) -> Path:
    import shutil

    dest = dest_parent / "project"
    shutil.copytree(fixture_root, dest)
    return dest


def _set_graph_authoring(project_root: Path) -> None:
    """Declare graph authoring so finalize exports the md view (graph → md)."""
    import json

    from cataforge.domain.kg._dispatch import invalidate_cache

    fw = project_root / ".cataforge" / "framework.json"
    data = json.loads(fw.read_text(encoding="utf-8"))
    data.setdefault("context", {}).update({"strategy": "kg-first", "authoring": "graph"})
    fw.write_text(json.dumps(data), encoding="utf-8")
    invalidate_cache()


def _init_on_disk_store(project_root: Path) -> None:
    """Create the on-disk oxigraph store the context lifecycle reads/writes."""
    from cataforge.domain.kg import init_store
    from cataforge.domain.kg._dispatch import kg_config_for

    cfg = kg_config_for(project_root)
    handle = init_store(cfg, force=True)
    handle.close()


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from cataforge.domain.kg._dispatch import invalidate_cache

    invalidate_cache()
    monkeypatch.chdir(tmp_path)
    yield
    invalidate_cache()
