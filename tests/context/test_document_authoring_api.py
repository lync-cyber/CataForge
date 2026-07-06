"""author_document / update_document_meta / write_narrative order fidelity."""

from __future__ import annotations

import gc
import json
from pathlib import Path

import pytest

from cataforge.application.context import write as cw
from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
from cataforge.domain.kg._dispatch import invalidate_cache, kg_config_for
from cataforge.domain.kg._errors import KGEntityNotFoundError, KGValidationError


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    gc.collect()
    yield
    invalidate_cache()
    gc.collect()


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    (proj / "docs").mkdir()
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps(
            {
                "docs": {"doc_types": {"prd": "prd", "arch": "arch"}},
                "context": {
                    "mode": "graph",
                    "kg_active_doc_types": ["prd", "arch", "test-report"],
                },
                "kg": {
                    "project_id": "proj-test",
                    "title": "Test",
                    "process_model": "waterfall",
                },
            }
        ),
        encoding="utf-8",
    )
    invalidate_cache()
    cfg = kg_config_for(proj)
    handle = init_store(cfg, force=True)
    handle.raw.flush()
    handle.close()
    invalidate_cache()
    gc.collect()
    return proj


def _connect(proj: Path) -> KGConfig:
    return kg_config_for(proj)


def _ns(cfg: KGConfig) -> str:
    return cfg.ontology_namespace.rstrip("/") + "/"


# A prd defines Feature + AcceptanceCriteria (authoritative doc_type); the
# F-002 → F-001 xref yields one cf:depends_on relation with both endpoints
# present, so the post-commit validate passes.
_PRD = (
    "---\n"
    "id: prd\n"
    "doc_type: prd\n"
    "status: draft\n"
    'version: "0.1.0"\n'
    "---\n"
    "\n"
    "# PRD\n"
    "\n"
    "Intro prose.\n"
    "\n"
    "## §1 Features\n"
    "\n"
    "### F-001 用户登录\n"
    "\n"
    "用户可用邮箱登录。\n"
    "\n"
    "- AC-001: 支持邮箱格式校验\n"
    "\n"
    "## §2 依赖\n"
    "\n"
    "### F-002 单点登录\n"
    "\n"
    "依赖 prd#§1.F-001 的基础登录。\n"
)


# ---- author_document end-to-end ---------------------------------------------


def test_author_document_roundtrips_byte_exact(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    result = cw.author_document(str(proj), _PRD)
    gc.collect()
    assert result.doc_id == "prd"
    # §1, F-001, §2, F-002 — every heading at level >= 2 becomes a Section.
    assert result.sections_written == 4
    assert result.entities_written == 3  # F-001, AC-001, F-002
    assert result.relations_written == 1  # F-002 depends_on F-001

    out = tmp_path / "out"
    cw.finalize(str(proj), str(out))
    gc.collect()
    rebuilt = (out / "prd" / "prd.md").read_text(encoding="utf-8")
    assert rebuilt == _PRD


def test_author_document_writes_entities_and_relation(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.author_document(str(proj), _PRD)
    gc.collect()
    cfg = _connect(proj)
    ns = _ns(cfg)
    with KnowledgeGraph.connect(cfg) as kg:
        assert kg.query.exists("F-001")
        assert kg.query.exists("F-002")
        ac_iri = "https://cataforge.dev/instance/F-001/AC-001"
        assert kg.store.query(
            f"ASK {{ <{ac_iri}> <{ns}part_of> <https://cataforge.dev/instance/F-001> }}"
        )
        assert kg.store.query(
            f"ASK {{ <https://cataforge.dev/instance/F-002> "
            f"<{ns}depends_on> <https://cataforge.dev/instance/F-001> }}"
        )
    gc.collect()


def test_reauthor_clears_stale_relation_edge(tmp_path: Path) -> None:
    """Re-authoring a document atomically replaces its traceability edges.

    A stale edge whose subject entity is unchanged across the re-author (so
    its content hash matches and the entity write is skipped) must still be
    removed — relation edges are not gated by the entity content hash."""
    proj = _project(tmp_path)
    cw.author_document(str(proj), _PRD)
    gc.collect()
    cfg = _connect(proj)
    ns = _ns(cfg)
    inst = "https://cataforge.dev/instance"
    phantom = f"ASK {{ <{inst}/F-001> <{ns}depends_on> <{inst}/F-002> }}"
    real = f"ASK {{ <{inst}/F-002> <{ns}depends_on> <{inst}/F-001> }}"

    # Inject a phantom edge F-001 -> F-002 the source never declares. F-001's
    # body is unchanged, so the next author run skips its entity write. The
    # write handle holds a RocksDB lock; a nested scope drops every reference
    # (facade + transaction) so the lock releases before re-authoring.
    def _inject_phantom() -> None:
        with KnowledgeGraph.connect(cfg) as kg:
            with kg.transaction() as txn:
                txn.add_relation("F-001", "cf:depends_on", "F-002")
            assert kg.store.query(phantom)

    _inject_phantom()
    gc.collect()

    # Re-author the identical source.
    cw.author_document(str(proj), _PRD)
    gc.collect()

    def _read() -> tuple[bool, bool]:
        with KnowledgeGraph.connect(cfg, read_only=True) as kg:
            return bool(kg.store.query(phantom)), bool(kg.store.query(real))

    phantom_present, real_present = _read()
    gc.collect()
    assert not phantom_present, "stale edge must be cleared on re-author"
    assert real_present, "the declared edge must survive"


def test_author_document_placeholder_title_fails(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    md = (
        "---\nid: prd\ndoc_type: prd\n---\n\n# PRD\n\n"
        "## §1 Features\n\n### F-001 {功能名称}\n\nbody\n"
    )
    with pytest.raises(KGValidationError, match="placeholder"):
        cw.author_document(str(proj), md)
    gc.collect()
    cfg = _connect(proj)
    with KnowledgeGraph.connect(cfg) as kg:
        assert kg.query.entity_ids() == set()
    gc.collect()


def test_author_document_set_literal_braces_in_title_allowed(tmp_path: Path) -> None:
    """A comma/顿号-separated set literal in an entity title is not a template token."""
    proj = _project(tmp_path)
    md = (
        "---\nid: prd\ndoc_type: prd\n---\n\n# PRD\n\n"
        "## §1 Features\n\n### F-001 支持 {C, F, K} 三种单位\n\nbody\n"
    )
    result = cw.author_document(str(proj), md)
    gc.collect()
    assert result.entities_written == 1


def test_author_document_placeholder_in_section_body_allowed(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    md = "---\nid: prd\ndoc_type: prd\n---\n\n# PRD\n\n## §1 概览\n\n占位 {TBD} 内容保留。\n"
    result = cw.author_document(str(proj), md)
    gc.collect()
    assert result.sections_written == 1


def test_author_document_missing_doc_type_fails(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    md = "---\nid: prd\n---\n\n# PRD\n\n## §1\n\nbody\n"
    with pytest.raises(KGValidationError, match="doc_type"):
        cw.author_document(str(proj), md)
    gc.collect()


def test_author_document_missing_id_fails(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    md = "---\ndoc_type: prd\n---\n\n# PRD\n\n## §1\n\nbody\n"
    with pytest.raises(KGValidationError, match="id"):
        cw.author_document(str(proj), md)
    gc.collect()


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_author_document_bad_frontmatter_fails(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    md = "---\nid: [unclosed\n---\n# body\n"
    with pytest.raises(KGValidationError, match="parse error"):
        cw.author_document(str(proj), md)
    gc.collect()


def test_author_document_validation_failure_zero_residue(tmp_path: Path) -> None:
    """A dangling xref target trips post-commit validate; the whole write
    (document + sections + entities) compensates to zero residue."""
    proj = _project(tmp_path)
    md = (
        "---\nid: prd\ndoc_type: prd\n---\n\n# PRD\n\n"
        "## §1 Features\n\n### F-001 单点登录\n\n依赖 prd#§9.F-404 的基础登录。\n"
    )
    with pytest.raises(KGValidationError):
        cw.author_document(str(proj), md)
    gc.collect()
    cfg = _connect(proj)
    ns = _ns(cfg)
    with KnowledgeGraph.connect(cfg) as kg:
        assert kg.query.entity_ids() == set()
        doc_count = list(
            kg.store.query(
                f"PREFIX cf: <{ns}> SELECT (COUNT(?d) AS ?n) WHERE {{ ?d a cf:Document }}"
            )
        )
        assert int(doc_count[0]["n"].value) == 0
        sec_count = list(
            kg.store.query(
                f"PREFIX cf: <{ns}> SELECT (COUNT(?s) AS ?n) WHERE {{ ?s a cf:Section }}"
            )
        )
        assert int(sec_count[0]["n"].value) == 0
    gc.collect()


# ---- update_document_meta ---------------------------------------------------


def test_update_document_meta_status_reflected_after_finalize(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.author_document(str(proj), _PRD)
    gc.collect()
    cw.update_document_meta(str(proj), "prd", status="approved")
    gc.collect()

    out = tmp_path / "out"
    cw.finalize(str(proj), str(out))
    gc.collect()
    rebuilt = (out / "prd" / "prd.md").read_text(encoding="utf-8")
    assert "status: approved" in rebuilt
    assert "status: draft" not in rebuilt


def test_update_document_meta_preserves_version_quote_style(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.author_document(str(proj), _PRD)
    gc.collect()
    cw.update_document_meta(str(proj), "prd", version="0.2.0")
    gc.collect()

    out = tmp_path / "out"
    cw.finalize(str(proj), str(out))
    gc.collect()
    rebuilt = (out / "prd" / "prd.md").read_text(encoding="utf-8")
    # The source carried a quoted `version: "0.1.0"`; the quote style survives.
    assert 'version: "0.2.0"' in rebuilt
    assert 'version: "0.1.0"' not in rebuilt


def test_update_document_meta_invalid_status_fails(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.author_document(str(proj), _PRD)
    gc.collect()
    with pytest.raises(KGValidationError, match="status"):
        cw.update_document_meta(str(proj), "prd", status="closed")
    gc.collect()


def test_update_document_meta_missing_document_fails(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with pytest.raises(KGEntityNotFoundError):
        cw.update_document_meta(str(proj), "prd", status="approved")
    gc.collect()


# ---- write_narrative order fidelity -----------------------------------------


def test_write_narrative_auto_prepends_heading(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.author_document(str(proj), _PRD)
    gc.collect()
    # Append a brand-new section via write_narrative with no heading line.
    cw.write_narrative(str(proj), doc_id="prd", anchor="§3 附录", narrative="附录正文。")
    gc.collect()

    out = tmp_path / "out"
    cw.finalize(str(proj), str(out))
    gc.collect()
    rebuilt = (out / "prd" / "prd.md").read_text(encoding="utf-8")
    assert "## §3 附录" in rebuilt
    assert "附录正文。" in rebuilt
    # Appended after the existing sections, not before them.
    assert rebuilt.index("§1 Features") < rebuilt.index("§3 附录")


def test_write_narrative_heading_anchor_mismatch_fails(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.author_document(str(proj), _PRD)
    gc.collect()
    with pytest.raises(KGValidationError, match="anchor"):
        cw.write_narrative(str(proj), doc_id="prd", anchor="§3 附录", narrative="## 错误标题\n正文")
    gc.collect()


def test_write_narrative_mid_doc_update_keeps_order(tmp_path: Path) -> None:
    """Updating one middle section must not reset its position (the core fix)."""
    proj = _project(tmp_path)
    cw.author_document(str(proj), _PRD)
    gc.collect()

    # Rewrite §1 Features' body — its heading line stays, anchor matches.
    cw.write_narrative(
        str(proj),
        doc_id="prd",
        anchor="§1 Features",
        narrative="## §1 Features\n\n改写后的特性章节正文。\n",
    )
    gc.collect()

    out = tmp_path / "out"
    cw.finalize(str(proj), str(out))
    gc.collect()
    rebuilt = (out / "prd" / "prd.md").read_text(encoding="utf-8")
    assert "改写后的特性章节正文。" in rebuilt
    # §1 must still precede §2 — position was not reset to 0.
    assert rebuilt.index("§1 Features") < rebuilt.index("§2 依赖")
