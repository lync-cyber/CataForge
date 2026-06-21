"""Authority-override consistency across the KG read / repair / author surface.

`extract_entities` resolves a class's authoritative doc_type(s) from
`context.kg_definition_authority`. Import already passes the project override;
reconcile, repair, compare-read and author_document must resolve the same
override, otherwise an entity defined in a non-default doc_type appears as a
ghost on one side of the pipeline while import wrote it on the other.

Scenario: a project authorises `Component` (default authority `arch`) to be
defined in `ui-spec`. A `### C-001 顶栏` heading then defines a Component in a
ui-spec volume.
"""

from __future__ import annotations

import gc
import json
from pathlib import Path

import pytest

from cataforge.domain.kg._dispatch import invalidate_cache

_FRAMEWORK_JSON = {
    "docs": {"doc_types": {"ui-spec": "ui-spec"}},
    "context": {
        "mode": "hybrid",
        "kg_active_doc_types": ["ui-spec"],
        "kg_definition_authority": {"Component": ["ui-spec"]},
    },
    "kg": {"project_id": "proj-test", "title": "Test", "process_model": "waterfall"},
}

_UI_SPEC_DOC = (
    "---\nid: ui-spec\ndoc_type: ui-spec\n---\n"
    "# UI Spec\n\n## §3 组件\n\n### C-001 顶栏\n\n顶部导航栏组件。\n"
)


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    gc.collect()
    yield
    invalidate_cache()
    gc.collect()


def _project(tmp_path: Path, *, mode: str | None = None) -> Path:
    proj = tmp_path / "proj"
    (proj / ".cataforge").mkdir(parents=True)
    cfg = _FRAMEWORK_JSON
    if mode is not None:
        cfg = {**_FRAMEWORK_JSON, "context": {**_FRAMEWORK_JSON["context"], "mode": mode}}
    (proj / ".cataforge" / "framework.json").write_text(json.dumps(cfg), encoding="utf-8")
    doc_dir = proj / "docs" / "ui-spec"
    doc_dir.mkdir(parents=True)
    (doc_dir / "ui-spec.md").write_text(_UI_SPEC_DOC, encoding="utf-8")
    invalidate_cache()
    return proj


def test_reconcile_honours_authority_extension(tmp_path: Path) -> None:
    """Import writes C-001 under the override; reconcile must recognise the same
    FS definition instead of flagging the imported node as a ghost."""
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration
    from cataforge.domain.kg.reconcile import reconcile

    proj = _project(tmp_path)
    config = KGConfig(store_backend="memory", kg_active_doc_types={"ui-spec"})
    handle = init_store(config, force=True)
    run_migration(handle.raw, proj, config, doc_types=("ui-spec",))

    report = reconcile(handle.raw, proj, config)
    per = report.per_doc_type["ui-spec"]
    assert per.ghost_entities == []
    assert per.missing_entities == []


def test_repair_reingest_honours_authority_extension(tmp_path: Path) -> None:
    """An empty graph plus an override-defined FS entity: repair must reingest
    C-001 (its reingest extraction has to resolve the override too)."""
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.reconcile import reconcile
    from cataforge.domain.kg.repair import repair

    proj = _project(tmp_path)
    config = KGConfig(store_backend="memory", kg_active_doc_types={"ui-spec"})
    handle = init_store(config, force=True)

    repair(handle.raw, proj, config, dry_run=False)

    # repair must have reingested the override-defined C-001 into the graph;
    # a no-op repair (reconcile blind to the override) leaves it absent.
    ns = config.ontology_namespace
    assert handle.raw.query(f'PREFIX cf: <{ns}> ASK {{ ?s cf:entity_id "C-001" }}')

    report = reconcile(handle.raw, proj, config)
    per = report.per_doc_type["ui-spec"]
    assert per.missing_entities == []
    assert per.ghost_entities == []


def test_compare_read_honours_authority_extension(tmp_path: Path) -> None:
    """compare-read's FS pool must include the override-defined C-001, so a
    post-ingest body mutation surfaces as a content-hash alarm rather than being
    silently skipped."""
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg.compare_read import compare_read
    from cataforge.domain.kg.ingest import run_migration

    proj = _project(tmp_path)
    db_path = proj / ".cataforge" / "kg" / "store"
    config = KGConfig(store_backend="oxigraph", db_path=db_path, kg_active_doc_types={"ui-spec"})
    handle = init_store(config, force=True)
    run_migration(handle.raw, proj, config, doc_types=("ui-spec",))
    del handle
    gc.collect()
    invalidate_cache()

    doc = proj / "docs" / "ui-spec" / "ui-spec.md"
    doc.write_text(
        _UI_SPEC_DOC.replace("顶部导航栏组件。", "顶部导航栏组件（改）。"), encoding="utf-8"
    )

    with KnowledgeGraph.connect(config) as kg:
        report = compare_read(kg, proj, doc_types={"ui-spec"}, sample_size=100, seed=42)
    gc.collect()

    assert any(a.entity_id == "C-001" for a in report.alarms), [a.to_dict() for a in report.alarms]


def test_author_document_honours_authority_extension(tmp_path: Path) -> None:
    """Authoring a ui-spec doc under kg-first must write C-001 as an entity; the
    write-path extraction has to resolve the override."""
    from cataforge.application.context import write as cw
    from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
    from cataforge.domain.kg._dispatch import kg_config_for

    proj = _project(tmp_path, mode="graph")
    cfg = kg_config_for(proj)
    handle = init_store(cfg, force=True)
    handle.raw.flush()
    handle.close()
    del handle
    invalidate_cache()
    gc.collect()

    result = cw.author_document(str(proj), _UI_SPEC_DOC)
    gc.collect()
    assert result.entities_written == 1

    config = KGConfig(
        store_backend="oxigraph",
        db_path=proj / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"ui-spec"},
    )
    with KnowledgeGraph.connect(config) as kg:
        assert kg.query.exists("C-001")
    gc.collect()
