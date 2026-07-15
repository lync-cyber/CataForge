"""Whole-document replace semantics on the authoring write path.

Re-authoring a document is a replace, not an accreting upsert: sections the
new revision no longer carries leave the graph (and the finalize export) in
the same transaction, and an entity whose content hash is unchanged still
follows its new home document.
"""

from __future__ import annotations

import gc
import json
from pathlib import Path

import pytest

from cataforge.application.context import write as cw
from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
from cataforge.domain.kg._dispatch import invalidate_cache

_FRAMEWORK = {
    "context": {"mode": "graph", "kg_active_doc_types": ["dev-plan", "prd"]},
    "kg": {"project_id": "p", "title": "T", "process_model": "waterfall"},
    "docs": {"doc_types": {"dev-plan": "dev-plan", "prd": "prd"}},
}

_NS = "PREFIX cf: <https://cataforge.dev/ontology/> "

_TWO_SECTION_PLAN = (
    "---\nid: dev-plan\ndoc_type: dev-plan\nstatus: draft\n---\n"
    "# Dev Plan\n\n## 3. 任务卡详细\n\n### T-001 登录\n\n实现登录。\n\n"
    "## 4. 里程碑\n\n第一里程碑。\n"
)
_ONE_SECTION_PLAN = (
    "---\nid: dev-plan\ndoc_type: dev-plan\nstatus: draft\n---\n"
    "# Dev Plan\n\n## 3. 任务卡详细\n\n### T-001 登录\n\n实现登录。\n"
)


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    gc.collect()
    yield
    invalidate_cache()
    gc.collect()


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / ".cataforge").mkdir(parents=True)
    cfg = KGConfig(store_backend="oxigraph", db_path=proj / ".cataforge" / "kg" / "store")
    init_store(cfg, force=True).close()
    (proj / ".cataforge" / "framework.json").write_text(json.dumps(_FRAMEWORK), encoding="utf-8")
    (proj / "docs").mkdir()
    invalidate_cache()
    gc.collect()
    return proj


def _values(proj: Path, sparql: str) -> list[str]:
    from cataforge.domain.kg._dispatch import kg_config_for

    cfg = kg_config_for(str(proj))
    with KnowledgeGraph.connect(cfg, read_only=True) as kg:
        return sorted(str(row[0].value) for row in kg.store.query(sparql) if row[0] is not None)


def test_re_author_removes_stale_sections(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.author_document(str(proj), _TWO_SECTION_PLAN, source_path="docs/dev-plan/dev-plan.md")
    gc.collect()

    cw.author_document(str(proj), _ONE_SECTION_PLAN, source_path="docs/dev-plan/dev-plan.md")
    gc.collect()

    anchors = _values(
        proj,
        _NS + 'SELECT ?a WHERE { ?s a cf:Section ; cf:source_doc "dev-plan" ; '
        "cf:section_anchor ?a }",
    )
    assert not any("里程碑" in a for a in anchors), anchors

    cw.finalize(str(proj))
    gc.collect()
    exported = (proj / "docs" / "dev-plan" / "dev-plan.md").read_text(encoding="utf-8")
    assert "里程碑" not in exported


def test_re_author_syncs_unchanged_subordinate_source_section(tmp_path: Path) -> None:
    # AC-001's hash covers only its own bullet line; renaming the owning task
    # heading leaves the hash unchanged, so a plain upsert would skip it and
    # leave `cf:source_section` pointing at the old heading.
    doc = (
        "---\nid: dev-plan\ndoc_type: dev-plan\nstatus: draft\n---\n"
        "# Dev Plan\n\n## 3. 任务卡详细\n\n### T-001 登录\n\n- AC-001: 编译通过\n"
    )
    proj = _project(tmp_path)
    cw.author_document(str(proj), doc, source_path="docs/dev-plan/dev-plan.md")
    gc.collect()

    cw.author_document(
        str(proj),
        doc.replace("### T-001 登录", "### T-001 用户登录"),
        source_path="docs/dev-plan/dev-plan.md",
    )
    gc.collect()

    sections = _values(
        proj,
        _NS + 'SELECT ?sec WHERE { ?s cf:entity_id "AC-001" ; cf:source_section ?sec }',
    )
    assert sections == ["T-001 用户登录"], sections
