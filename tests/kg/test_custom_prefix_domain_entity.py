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
        "---\ndoc_id: prd\n---\n# PRD\n\n## §2\n\n### F-003 下单\n\n下单功能。\n",
    )
    _write(
        tmp_path,
        "dev-plan",
        "dev-plan.md",
        "---\ndoc_id: dev-plan\n---\n# Dev Plan\n\n## §3\n\n"
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
