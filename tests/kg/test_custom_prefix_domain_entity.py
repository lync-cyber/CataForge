"""O2: config-aware entity-id prefixes — the DomainEntity escape hatch.

A downstream project registers custom prefixes in framework.json
``kg.custom_entity_prefixes``; a registered id materializes as a DomainEntity
carrying its domain_type, and its traceability edges reach core entities.
Without registration core extraction is unchanged (the id is not matched).
"""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.domain.kg import KGConfig, init_store
from cataforge.domain.kg._dispatch import invalidate_cache
from cataforge.domain.kg.ingest import run_migration

_CF = "PREFIX cf: <https://cataforge.dev/ontology/> "


def _write(root: Path, doc_type: str, name: str, body: str) -> None:
    d = root / "docs" / doc_type
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def _framework(root: Path, custom_prefixes: dict[str, str]) -> None:
    (root / ".cataforge").mkdir(exist_ok=True)
    (root / ".cataforge" / "framework.json").write_text(
        json.dumps(
            {
                "context": {"mode": "graph", "kg_active_doc_types": ["prd", "dev-plan"]},
                "kg": {
                    "project_id": "p",
                    "title": "T",
                    "process_model": "waterfall",
                    "custom_entity_prefixes": custom_prefixes,
                },
            }
        ),
        encoding="utf-8",
    )


def _project(tmp_path: Path, custom_prefixes: dict[str, str]):
    _write(
        tmp_path,
        "prd",
        "prd.md",
        "---\nid: prd\n---\n# PRD\n\n## §2\n\n### F-003 下单\n\n下单功能。\n",
    )
    _write(
        tmp_path,
        "dev-plan",
        "dev-plan.md",
        "---\nid: dev-plan\n---\n# Dev Plan\n\n## §3\n\n"
        "### ORD-001 订单聚合\n\n满足 AC: prd#§2.F-003\n",
    )
    _framework(tmp_path, custom_prefixes)
    invalidate_cache()
    config = KGConfig(store_backend="memory", kg_active_doc_types={"prd", "dev-plan"})
    handle = init_store(config, force=True)
    stats, _, _ = run_migration(handle.raw, tmp_path, config, doc_types=("prd", "dev-plan"))
    assert stats.verify_result is not None and stats.verify_result.ok, stats.to_dict()
    return handle


def test_registered_prefix_becomes_domain_entity(tmp_path: Path) -> None:
    handle = _project(tmp_path, {"ORD": "Order"})
    rows = list(
        handle.raw.query(
            _CF + 'SELECT ?dt WHERE { ?s cf:entity_id "ORD-001" ; a cf:DomainEntity ; '
            "cf:domain_type ?dt }"
        )
    )
    assert [str(r["dt"].value) for r in rows] == ["Order"]


def test_registered_domain_entity_traceability_edge_reaches_core(tmp_path: Path) -> None:
    handle = _project(tmp_path, {"ORD": "Order"})
    rows = list(
        handle.raw.query(_CF + 'SELECT ?o WHERE { ?s cf:entity_id "ORD-001" ; cf:satisfies ?o }')
    )
    assert [str(r["o"].value) for r in rows] == ["https://cataforge.dev/instance/F-003"]


def test_unregistered_prefix_is_not_extracted(tmp_path: Path) -> None:
    # No registration → ORD-001 is not matched at all; core F-003 still lands.
    handle = _project(tmp_path, {})
    ord_rows = list(handle.raw.query(_CF + 'SELECT ?s WHERE { ?s cf:entity_id "ORD-001" }'))
    assert ord_rows == []
    f_rows = list(handle.raw.query(_CF + 'SELECT ?s WHERE { ?s cf:entity_id "F-003" }'))
    assert len(f_rows) == 1


def test_author_document_recognizes_registered_prefix(tmp_path: Path) -> None:
    import gc

    from cataforge.application.context import write as cw
    from cataforge.domain.kg import KnowledgeGraph

    proj = tmp_path / "proj"
    (proj / ".cataforge").mkdir(parents=True)
    cfg = KGConfig(store_backend="oxigraph", db_path=proj / ".cataforge" / "kg" / "store")
    init_store(cfg, force=True).close()
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps(
            {
                "context": {"mode": "graph", "kg_active_doc_types": ["dev-plan"]},
                "kg": {
                    "project_id": "p",
                    "title": "T",
                    "process_model": "waterfall",
                    "custom_entity_prefixes": {"ORD": "Order"},
                },
                "docs": {"doc_types": {"dev-plan": "dev-plan"}},
            }
        ),
        encoding="utf-8",
    )
    (proj / "docs").mkdir()
    invalidate_cache()
    gc.collect()

    md = (
        "---\nid: dev-plan\ndoc_type: dev-plan\nstatus: draft\n---\n"
        "# Dev Plan\n\n## 3. 任务卡\n\n### ORD-001 订单聚合\n\n聚合订单。\n"
    )
    cw.author_document(str(proj), md, source_path="docs/dev-plan/dev-plan.md")
    gc.collect()

    with KnowledgeGraph.connect(cfg) as kg:
        rows = list(
            kg.store.query(
                _CF + 'SELECT ?dt WHERE { ?s cf:entity_id "ORD-001" ; a cf:DomainEntity ; '
                "cf:domain_type ?dt }"
            )
        )
        vals = [str(r["dt"].value) for r in rows]
    assert vals == ["Order"]


def test_domain_entity_attributes_are_queryable(tmp_path: Path) -> None:
    # `- key: value` bullets in a DomainEntity body → has_attribute → DomainAttribute.
    _write(
        tmp_path,
        "dev-plan",
        "dev-plan.md",
        "---\nid: dev-plan\n---\n# Dev Plan\n\n## §3\n\n"
        "### ORD-001 订单聚合\n\n- 状态: 已下单\n- 金额: 100\n",
    )
    _framework(tmp_path, {"ORD": "Order"})
    invalidate_cache()
    config = KGConfig(store_backend="memory", kg_active_doc_types={"dev-plan"})
    handle = init_store(config, force=True)
    stats, _, _ = run_migration(handle.raw, tmp_path, config, doc_types=("dev-plan",))
    assert stats.verify_result is not None and stats.verify_result.ok, stats.to_dict()

    rows = list(
        handle.raw.query(
            _CF + 'SELECT ?n ?v WHERE { ?s cf:entity_id "ORD-001" ; cf:has_attribute ?a . '
            "?a cf:attr_name ?n ; cf:attr_value ?v } ORDER BY ?n"
        )
    )
    pairs = [(str(r["n"].value), str(r["v"].value)) for r in rows]
    assert pairs == [("状态", "已下单"), ("金额", "100")]


def test_schema_card_documents_domain_extension() -> None:
    from cataforge.domain.kg.schema_context import build_schema_card

    card = build_schema_card(custom_prefixes={"ORD": "Order"})
    assert "DomainEntity" in card
    assert "custom_entity_prefixes" in card
    assert "ORD" in card and "Order" in card


def test_schema_card_without_registration_still_documents_class() -> None:
    from cataforge.domain.kg.schema_context import build_schema_card

    card = build_schema_card()
    assert "cf:DomainEntity" in card


def test_reconcile_reports_clean_with_registered_prefix(tmp_path: Path) -> None:
    from cataforge.domain.kg.reconcile import reconcile

    handle = _project(tmp_path, {"ORD": "Order"})
    config = KGConfig(store_backend="memory", kg_active_doc_types={"prd", "dev-plan"})
    report = reconcile(handle.raw, tmp_path, config)
    per = report.per_doc_type["dev-plan"]
    assert per.ghost_entities == [], per.ghost_entities
    assert per.missing_entities == [], per.missing_entities


def test_repair_keeps_registered_domain_entity(tmp_path: Path) -> None:
    from cataforge.domain.kg.repair import repair

    handle = _project(tmp_path, {"ORD": "Order"})
    config = KGConfig(store_backend="memory", kg_active_doc_types={"prd", "dev-plan"})
    stats = repair(handle.raw, tmp_path, config)
    assert stats.ghosts_removed == 0, stats
    rows = list(handle.raw.query(_CF + 'SELECT ?s WHERE { ?s cf:entity_id "ORD-001" }'))
    assert len(rows) == 1, rows


def test_attribute_update_and_removal_replaces_projection(tmp_path: Path) -> None:
    # Re-ingesting a changed body must replace the attr projection: an updated
    # value may not accumulate, a removed bullet may not leave an orphan node.
    _framework(tmp_path, {"ORD": "Order"})
    base = "---\nid: dev-plan\n---\n# Dev Plan\n\n## §3\n\n### ORD-001 订单聚合\n\n"
    _write(tmp_path, "dev-plan", "dev-plan.md", base + "- 状态: 已下单\n- 金额: 100\n")
    invalidate_cache()
    config = KGConfig(store_backend="memory", kg_active_doc_types={"dev-plan"})
    handle = init_store(config, force=True)
    run_migration(handle.raw, tmp_path, config, doc_types=("dev-plan",))

    _write(tmp_path, "dev-plan", "dev-plan.md", base + "- 状态: 已发货\n")
    run_migration(handle.raw, tmp_path, config, doc_types=("dev-plan",))

    rows = list(
        handle.raw.query(
            _CF + 'SELECT ?v WHERE { ?s cf:entity_id "ORD-001" ; cf:has_attribute ?a . '
            "?a cf:attr_value ?v }"
        )
    )
    assert [str(r["v"].value) for r in rows] == ["已发货"], rows
    orphans = list(handle.raw.query(_CF + 'SELECT ?a WHERE { ?a cf:attr_name "金额" }'))
    assert orphans == [], orphans


def test_write_doc_projects_attributes(tmp_path: Path) -> None:
    # The graph-mode authoring path (context write-doc) must project
    # DomainAttribute sub-nodes the same way `kg import` does.
    import gc

    from cataforge.application.context import write as cw
    from cataforge.domain.kg import KnowledgeGraph
    from cataforge.domain.kg._dispatch import kg_config_for

    _framework(tmp_path, {"ORD": "Order"})
    invalidate_cache()
    cfg = kg_config_for(tmp_path)
    handle = init_store(cfg, force=True)
    handle.raw.flush()
    del handle
    gc.collect()
    invalidate_cache()

    cw.author_document(
        str(tmp_path),
        "---\nid: dev-plan\ndoc_type: dev-plan\n---\n# Dev Plan\n\n## §3\n\n"
        "### ORD-001 订单聚合\n\n- 状态: 已下单\n",
    )

    with KnowledgeGraph.connect(kg_config_for(tmp_path), read_only=True) as kg:
        rows = list(
            kg.store.query(
                _CF + 'SELECT ?n ?v WHERE { ?s cf:entity_id "ORD-001" ; cf:has_attribute ?a . '
                "?a cf:attr_name ?n ; cf:attr_value ?v }"
            )
        )
    pairs = [(str(r["n"].value), str(r["v"].value)) for r in rows]
    assert pairs == [("状态", "已下单")], pairs


def test_trace_from_requirement_includes_domain_entity(tmp_path: Path) -> None:
    # ORD-001 cf:satisfies F-003 — the trace chain rooted at the feature must
    # surface the DomainEntity neighbour instead of silently dropping it.
    from cataforge.domain.kg.trace import TraceAPI

    handle = _project(tmp_path, {"ORD": "Order"})
    config = KGConfig(store_backend="memory", kg_active_doc_types={"prd", "dev-plan"})
    chain = TraceAPI(handle.raw, config).from_requirement("F-003")
    assert "ORD-001" in chain.domain_entities, chain


def _graph_project(tmp_path: Path, custom_prefixes: dict[str, str]) -> tuple[Path, KGConfig]:
    import gc

    proj = tmp_path / "proj"
    (proj / ".cataforge").mkdir(parents=True)
    (proj / "docs").mkdir()
    cfg = KGConfig(store_backend="oxigraph", db_path=proj / ".cataforge" / "kg" / "store")
    init_store(cfg, force=True).close()
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps(
            {
                "context": {"mode": "graph", "kg_active_doc_types": ["dev-plan"]},
                "kg": {
                    "project_id": "p",
                    "title": "T",
                    "process_model": "waterfall",
                    "custom_entity_prefixes": custom_prefixes,
                },
            }
        ),
        encoding="utf-8",
    )
    invalidate_cache()
    gc.collect()
    return proj, cfg


def test_author_entity_accepts_registered_prefix(tmp_path: Path) -> None:
    from cataforge.application.context import write as cw
    from cataforge.domain.kg import KnowledgeGraph

    proj, cfg = _graph_project(tmp_path, {"ORD": "Order"})
    cw.author_entity(str(proj), entity_id="ORD-002", class_name="DomainEntity", title="订单聚合")
    with KnowledgeGraph.connect(cfg, read_only=True) as kg:
        rows = list(
            kg.store.query(
                _CF + 'SELECT ?dt WHERE { ?s cf:entity_id "ORD-002" ; a cf:DomainEntity ; '
                "cf:domain_type ?dt }"
            )
        )
        vals = [str(r["dt"].value) for r in rows]
    assert vals == ["Order"], vals


def test_author_entity_rejects_unregistered_prefix(tmp_path: Path) -> None:
    import pytest

    from cataforge.application.context import write as cw
    from cataforge.domain.kg._errors import KGValidationError

    proj, _cfg = _graph_project(tmp_path, {})
    with pytest.raises(KGValidationError, match="no schema-known prefix"):
        cw.author_entity(
            str(proj), entity_id="ORD-002", class_name="DomainEntity", title="订单聚合"
        )


def test_build_prefix_registry_rejects_malformed_prefix() -> None:
    import pytest

    from cataforge.domain.kg.ingest.entity_extract import build_prefix_registry

    with pytest.raises(ValueError, match="uppercase"):
        build_prefix_registry({"ord": "Order"})
