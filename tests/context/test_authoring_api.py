"""P-2 authoring API: parent/relations/narrative on author_entity + transact."""

from __future__ import annotations

import gc
import json
from pathlib import Path

import pytest

from cataforge.application.context import write as cw
from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
from cataforge.domain.kg._dispatch import invalidate_cache
from cataforge.domain.kg._errors import KGValidationError


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
    cfg = KGConfig(
        store_backend="oxigraph",
        db_path=proj / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test-report"},
    )
    handle = init_store(cfg, force=True)
    handle.raw.flush()
    handle.close()
    ctx = {"strategy": "kg-first", "kg_active_doc_types": ["prd", "arch", "test-report"]}
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": ctx}), encoding="utf-8"
    )
    invalidate_cache()
    gc.collect()
    return proj


def _connect(proj: Path) -> KGConfig:
    return KGConfig(
        store_backend="oxigraph",
        db_path=proj / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test-report"},
    )


def _ns(cfg: KGConfig) -> str:
    return cfg.ontology_namespace.rstrip("/") + "/"


def _ask(kg: KnowledgeGraph, sparql: str) -> bool:
    from cataforge.domain.kg._ask import ask

    return ask(kg.store, sparql)


def _edge_count(kg: KnowledgeGraph, ns: str) -> int:
    rows = list(
        kg.store.query(
            f"PREFIX cf: <{ns}> SELECT (COUNT(*) AS ?n) WHERE {{ "
            "?s ?p ?o . FILTER(?p = cf:implements || ?p = cf:verifies || ?p = cf:part_of) }"
        )
    )
    return int(rows[0]["n"].value)


# ---- author_entity: parent + relations + narrative --------------------------


def test_author_entity_with_parent_scopes_iri_and_part_of(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.author_entity(str(proj), entity_id="F-001", class_name="Feature", title="登录")
    gc.collect()
    iri = cw.author_entity(
        str(proj),
        entity_id="AC-001",
        class_name="AcceptanceCriteria",
        title="可用邮箱登录",
        parent_id="F-001",
    )
    gc.collect()
    assert iri.endswith("F-001/AC-001")
    cfg = _connect(proj)
    ns = _ns(cfg)
    with KnowledgeGraph.connect(cfg) as kg:
        assert _ask(kg, f"ASK {{ <{iri}> <{ns}part_of> <https://cataforge.dev/instance/F-001> }}")
    gc.collect()


def test_author_entity_with_relations_writes_edges(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.author_entity(str(proj), entity_id="F-001", class_name="Feature", title="登录")
    gc.collect()
    cw.author_entity(
        str(proj),
        entity_id="M-001",
        class_name="Module",
        title="认证模块",
        relations=[("implements", "F-001")],
    )
    gc.collect()
    cfg = _connect(proj)
    ns = _ns(cfg)
    with KnowledgeGraph.connect(cfg) as kg:
        assert _ask(
            kg,
            f"ASK {{ <https://cataforge.dev/instance/M-001> "
            f"<{ns}implements> <https://cataforge.dev/instance/F-001> }}",
        )
    gc.collect()


def test_author_entity_with_narrative_writes_body_slot(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.author_entity(
        str(proj),
        entity_id="F-001",
        class_name="Feature",
        title="登录",
        narrative="用户通过邮箱与密码登录系统。\n支持记住登录状态。",
    )
    gc.collect()
    cfg = _connect(proj)
    ns = _ns(cfg)
    with KnowledgeGraph.connect(cfg) as kg:
        rows = list(
            kg.store.query(
                f"PREFIX cf: <{ns}> SELECT ?b WHERE {{ "
                "<https://cataforge.dev/instance/F-001> cf:narrative_body ?b }"
            )
        )
        assert rows and "记住登录状态" in str(rows[0]["b"].value)
    gc.collect()


def test_author_entity_failed_validation_compensates_relations(tmp_path: Path) -> None:
    """A post-write violation must roll back the entity AND its just-written
    relation edges — zero residue."""
    proj = _project(tmp_path)
    cw.author_entity(str(proj), entity_id="F-001", class_name="Feature", title="登录")
    gc.collect()

    # The relation points at a target that does not exist, tripping the
    # implements-target-exists shape post-commit; the module and its edge must
    # all be compensated away.
    with pytest.raises(KGValidationError):
        cw.author_entity(
            str(proj),
            entity_id="M-001",
            class_name="Module",
            title="认证模块",
            relations=[("implements", "F-404")],
        )
    gc.collect()

    cfg = _connect(proj)
    ns = _ns(cfg)
    with KnowledgeGraph.connect(cfg) as kg:
        assert not kg.query.exists("M-001")
        assert kg.query.entity_ids() == {"F-001"}
        assert _edge_count(kg, ns) == 0  # the dangling implements edge is gone
    gc.collect()


# ---- transact: single-transaction multi-op ----------------------------------


def test_transact_writes_feature_and_acs_atomically(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    ops = {
        "operations": [
            {"op": "add_entity", "entity_id": "F-001", "class": "Feature", "title": "登录"},
            *[
                {
                    "op": "add_entity",
                    "entity_id": f"AC-{i:03d}",
                    "class": "AcceptanceCriteria",
                    "title": f"验收 {i}",
                    "parent": "F-001",
                }
                for i in range(1, 11)
            ],
            {
                "op": "add_entity",
                "entity_id": "M-001",
                "class": "Module",
                "title": "认证模块",
                "relations": [["implements", "F-001"]],
            },
        ]
    }
    result = cw.transact(str(proj), ops)
    gc.collect()
    assert result.entities_written == 12

    cfg = _connect(proj)
    ns = _ns(cfg)
    with KnowledgeGraph.connect(cfg) as kg:
        assert kg.query.exists("F-001")
        assert kg.query.exists("M-001")
        ac_iri = "https://cataforge.dev/instance/F-001/AC-001"
        assert _ask(
            kg, f"ASK {{ <{ac_iri}> <{ns}part_of> <https://cataforge.dev/instance/F-001> }}"
        )
        assert _ask(
            kg,
            f"ASK {{ <https://cataforge.dev/instance/M-001> "
            f"<{ns}implements> <https://cataforge.dev/instance/F-001> }}",
        )
    gc.collect()


def test_transact_invalid_op_rolls_back_to_zero_residue(tmp_path: Path) -> None:
    proj = _project(tmp_path)

    ops = {
        "operations": [
            {"op": "add_entity", "entity_id": "F-001", "class": "Feature", "title": "登录"},
            # Wrong-class entity: AC-002 prefix maps to AcceptanceCriteria, not Module.
            {"op": "add_entity", "entity_id": "AC-002", "class": "Module", "title": "bad"},
        ]
    }
    with pytest.raises(KGValidationError):
        cw.transact(str(proj), ops)
    gc.collect()

    cfg = _connect(proj)
    ns = _ns(cfg)
    with KnowledgeGraph.connect(cfg) as kg:
        assert kg.query.entity_ids() == set()
        assert _edge_count(kg, ns) == 0
    gc.collect()


def test_transact_validation_failure_rolls_back_to_zero_residue(tmp_path: Path) -> None:
    """A post-commit validation violation (dangling relation target) rolls the
    whole transaction back — including the valid entities staged alongside it."""
    proj = _project(tmp_path)

    ops = {
        "operations": [
            {"op": "add_entity", "entity_id": "F-001", "class": "Feature", "title": "登录"},
            {
                "op": "add_entity",
                "entity_id": "M-001",
                "class": "Module",
                "title": "认证模块",
                "relations": [["implements", "F-404"]],
            },
        ]
    }
    with pytest.raises(KGValidationError):
        cw.transact(str(proj), ops)
    gc.collect()

    cfg = _connect(proj)
    ns = _ns(cfg)
    with KnowledgeGraph.connect(cfg) as kg:
        assert kg.query.entity_ids() == set()
        assert _edge_count(kg, ns) == 0
    gc.collect()


def test_transact_supports_write_narrative_op(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    ops = {
        "operations": [
            {"op": "add_entity", "entity_id": "F-001", "class": "Feature", "title": "登录"},
            {
                "op": "write_narrative",
                "doc_id": "prd",
                "anchor": "§1 概览",
                "narrative": "本章概述登录能力。",
            },
        ]
    }
    cw.transact(str(proj), ops)
    gc.collect()
    cfg = _connect(proj)
    ns = _ns(cfg)
    with KnowledgeGraph.connect(cfg) as kg:
        rows = list(
            kg.store.query(
                f"PREFIX cf: <{ns}> SELECT ?b WHERE {{ "
                '?s a cf:Section ; cf:source_doc "prd" ; cf:narrative_body ?b }'
            )
        )
        assert any("登录能力" in str(r["b"].value) for r in rows)
    gc.collect()


def test_transact_requires_kg_first(tmp_path: Path) -> None:
    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"strategy": "doc-only"}}), encoding="utf-8"
    )
    (proj / "docs").mkdir()
    invalidate_cache()
    gc.collect()
    with pytest.raises(cw.ContextStrategyError):
        cw.transact(str(proj), {"operations": []})
    gc.collect()
