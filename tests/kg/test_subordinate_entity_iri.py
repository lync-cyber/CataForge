"""Parent-scoped IRIs for subordinate entities (PR-2 / issue #210 fix B).

An AcceptanceCriteria id (AC-NNN) is local to its owning Feature/Task, so the
same id legitimately recurs under different parents. A flat project-global IRI
collapsed them onto one node (silent data loss + reconcile never converging).
They are now keyed `(parent_id, entity_id)` and minted at
`{base}/{parent_id}/{entity_id}`, so distinct parents yield distinct nodes.
"""

from __future__ import annotations

from pathlib import Path


def _parsed_doc(doc_id: str, doc_type: str, body: str):
    from cataforge.domain.kg.ingest.scan import (
        ParsedDoc,
        _code_block_char_ranges,
        heading_spans,
    )

    return ParsedDoc(
        doc_id=doc_id,
        doc_type=doc_type,
        file_path=Path(f"{doc_id}.md"),
        mtime=0.0,
        raw=body,
        body=body,
        body_offset=0,
        sections=heading_spans(body, 0),
        code_block_offsets=_code_block_char_ranges(body),
    )


# --- extraction: parent resolution + scoping ---------------------------------


def test_same_ac_id_under_different_parents_are_distinct() -> None:
    from cataforge.domain.kg.ingest.entity_extract import extract_entities

    body = (
        "# PRD\n\n## §2 Features\n\n"
        "### F-001 用户登录\n\n- AC-001: 邮箱密码可登录\n\n"
        "### F-002 用户登出\n\n- AC-001: 一键登出清空 token\n"
    )
    acs = [e for e in extract_entities(_parsed_doc("prd", "prd", body)) if e.entity_id == "AC-001"]
    parents = sorted(e.parent_id for e in acs)
    assert parents == ["F-001", "F-002"], "an AC-001 under each feature must both survive"
    assert sorted(e.scope_key for e in acs) == ["F-001/AC-001", "F-002/AC-001"]


def test_dev_plan_task_local_ac_not_collapsed() -> None:
    # The single-doc first-occurrence dedup used to drop every AC-001 but the
    # first; scoping by parent keeps each task's local acceptance criterion.
    from cataforge.domain.kg.ingest.entity_extract import extract_entities

    body = (
        "# Dev Plan\n\n## §5 Tasks\n\n"
        "### T-001 骨架\n\n- AC-001: 编译通过\n- AC-002: 冒烟通过\n\n"
        "### T-002 接口\n\n- AC-001: 契约测试通过\n"
    )
    entities = extract_entities(_parsed_doc("dev-plan", "dev-plan", body))
    ac_keys = sorted(e.scope_key for e in entities if e.entity_id.startswith("AC-"))
    assert ac_keys == ["T-001/AC-001", "T-001/AC-002", "T-002/AC-001"]
    assert {"T-001", "T-002"} <= {e.entity_id for e in entities}


def test_ac_with_own_heading_resolves_parent_not_itself() -> None:
    # When the AC has its own sub-heading, parent resolution must climb past it
    # to the owning Feature rather than treating the AC as its own parent.
    from cataforge.domain.kg.ingest.entity_extract import extract_entities

    body = "# PRD\n\n### §2.1 F-001 登录\n\n#### AC-001 可登录\n\n返回 200。\n"
    (ac,) = [
        e for e in extract_entities(_parsed_doc("prd", "prd", body)) if e.entity_id == "AC-001"
    ]
    assert ac.parent_id == "F-001"


def test_subordinate_iri_is_parent_scoped() -> None:
    from cataforge.domain.kg.ingest.iri import entity_iri, resolve_entity_iri

    composite = resolve_entity_iri(
        "AC-001", "AcceptanceCriteria", "F-001", "https://x.dev/instance"
    )
    assert composite == "https://x.dev/instance/F-001/AC-001"
    # Non-subordinate (or parentless) stays flat.
    assert resolve_entity_iri("F-001", "Feature", None, "https://x.dev/instance") == entity_iri(
        "F-001", "https://x.dev/instance"
    )
    assert resolve_entity_iri(
        "AC-001", "AcceptanceCriteria", None, "https://x.dev/instance"
    ) == entity_iri("AC-001", "https://x.dev/instance")


# --- migration + reconcile: end-to-end convergence ---------------------------


def _write(project_root: Path, doc_type: str, name: str, body: str) -> None:
    d = project_root / "docs" / doc_type
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def test_cross_doc_same_ac_id_imports_and_reconciles(tmp_path: Path) -> None:
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration
    from cataforge.domain.kg.reconcile import reconcile

    _write(
        tmp_path,
        "prd",
        "prd.md",
        "---\ndoc_id: prd\n---\n# PRD\n\n## §2\n\n"
        "### F-001 登录\n\n- AC-001: 邮箱密码可登录\n\n"
        "### F-002 登出\n\n- AC-001: 一键登出\n",
    )
    _write(
        tmp_path,
        "dev-plan",
        "dev-plan.md",
        "---\ndoc_id: dev-plan\n---\n# Dev Plan\n\n## §5\n\n### T-001 骨架\n\n- AC-001: 编译通过\n",
    )

    config = KGConfig(store_backend="memory", kg_active_doc_types={"prd", "dev-plan"})
    handle = init_store(config, force=True)

    # Must not abort on the (formerly colliding) repeated AC-001.
    stats, entities, _ = run_migration(handle.raw, tmp_path, config, doc_types=("prd", "dev-plan"))
    assert stats.verify_result is not None and stats.verify_result.ok, stats.to_dict()

    # Three distinct AC nodes — one per (parent, AC-001) — survive.
    ac_scope_keys = sorted(e.scope_key for e in entities if e.entity_id == "AC-001")
    assert ac_scope_keys == ["F-001/AC-001", "F-002/AC-001", "T-001/AC-001"]

    rows = list(
        handle.raw.query(
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s cf:entity_id 'AC-001' }".replace("'", '"')
        )
    )
    assert int(rows[0]["n"].value) == 3, "three parent-scoped AC-001 nodes expected"

    report = reconcile(handle.raw, tmp_path, config)
    assert report.overall_divergence_count == 0, report.to_dict()


def test_cross_doc_ac_xref_resolves_to_nested_node(tmp_path: Path) -> None:
    # A dev-plan xref names only the base doc + AC id (prd#§2.AC-001). The
    # satisfies edge must resolve to the AC's parent-scoped nested node
    # `{base}/F-001/AC-001`, not a bare flat placeholder `{base}/AC-001` (which
    # has no entity_id and gets filtered out of the AC-traceability check).
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    _write(
        tmp_path,
        "prd",
        "prd.md",
        "---\ndoc_id: prd\n---\n# PRD\n\n## §2\n\n### F-001 登录\n\n- AC-001: 邮箱密码可登录\n",
    )
    _write(
        tmp_path,
        "dev-plan",
        "dev-plan.md",
        "---\ndoc_id: dev-plan\n---\n# Dev Plan\n\n## §5\n\n"
        "### T-001 骨架\n\n满足 AC: prd#§2.AC-001\n",
    )

    config = KGConfig(store_backend="memory", kg_active_doc_types={"prd", "dev-plan"})
    handle = init_store(config, force=True)
    stats, _, _ = run_migration(handle.raw, tmp_path, config, doc_types=("prd", "dev-plan"))
    assert stats.verify_result is not None and stats.verify_result.ok, stats.to_dict()

    rows = list(
        handle.raw.query(
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            'SELECT ?obj WHERE { ?t cf:entity_id "T-001" . ?t cf:satisfies ?obj }'
        )
    )
    obj_iris = sorted(str(r["obj"].value) for r in rows)
    assert obj_iris == ["https://cataforge.dev/instance/F-001/AC-001"], obj_iris

    # The resolved endpoint must be the real AC node — i.e. it carries entity_id.
    eid_rows = list(
        handle.raw.query(
            "PREFIX cf: <https://cataforge.dev/ontology/> "
            "SELECT ?eid WHERE { "
            "<https://cataforge.dev/instance/F-001/AC-001> cf:entity_id ?eid }"
        )
    )
    assert [str(r["eid"].value) for r in eid_rows] == ["AC-001"]
