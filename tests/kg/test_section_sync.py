"""Cascade section sync: a narrative write at any heading depth must reach the
whole-document export and keep the level-2 tile-cover bodies and the per-section
nodes mutually consistent."""

from __future__ import annotations

import gc
import hashlib
from pathlib import Path

import pytest

from cataforge.application.context import write as cw
from cataforge.domain.kg import KnowledgeGraph
from cataforge.domain.kg._dispatch import invalidate_cache
from cataforge.domain.kg._errors import KGValidationError
from tests.kg.test_reconcile_triage import (
    PRD,
    _config,
    _finalized_project,
    _reconcile,
    _state_for,
)

pytestmark = pytest.mark.usefixtures("_isolate_cache")


@pytest.fixture
def _isolate_cache():
    invalidate_cache()
    yield
    invalidate_cache()


ANCHOR_L2_OVERVIEW = "§1 概览"
ANCHOR_L2_FEATURES = "§2 Features"
ANCHOR_L3_LOGIN = "§2.1 F-001 用户登录"
ANCHOR_L3_LOGOUT = "§2.2 F-002 用户登出"
ANCHOR_L4_AC_LOGIN = "AC-001 邮箱密码可登录"
ANCHOR_L4_AC_LOGOUT = "AC-002 一键登出清空 token"

AC_LOGIN_BLOCK = (
    "#### AC-001 邮箱密码可登录\n\n输入合法 (邮箱, 密码) 对返回 200 + JWT；失败返回 401。"
)


def _write(proj: Path, anchor: str, narrative: str) -> None:
    cw.write_narrative(str(proj), doc_id="prd", anchor=anchor, narrative=narrative)
    gc.collect()
    invalidate_cache()


def _finalize(proj: Path):
    result = cw.finalize(str(proj))
    gc.collect()
    invalidate_cache()
    return result


def _prd_path(proj: Path) -> Path:
    return proj.joinpath(*PRD)


def _section_body(proj: Path, anchor: str) -> str | None:
    with KnowledgeGraph.connect(_config(proj)) as kg:
        ns = kg.config.ontology_namespace.rstrip("/") + "/"
        safe = anchor.replace('"', '\\"')
        rows = list(
            kg.store.query(
                f"PREFIX cf: <{ns}> "
                'SELECT ?body WHERE { ?s a cf:Section ; cf:source_doc "prd" ; '
                f'cf:section_anchor "{safe}" ; cf:narrative_body ?body }}'
            )
        )
        return str(rows[0]["body"].value) if rows else None


def _contained_entity_ids(proj: Path, anchor: str) -> set[str]:
    with KnowledgeGraph.connect(_config(proj)) as kg:
        ns = kg.config.ontology_namespace.rstrip("/") + "/"
        safe = anchor.replace('"', '\\"')
        rows = list(
            kg.store.query(
                f"PREFIX cf: <{ns}> "
                'SELECT ?eid WHERE { ?s a cf:Section ; cf:source_doc "prd" ; '
                f'cf:section_anchor "{safe}" ; cf:contains_entity ?e . '
                "?e cf:entity_id ?eid }"
            )
        )
        return {str(row["eid"].value) for row in rows}


# --- silent-loss closure (issue-class: revisions must reach the export) -------


def test_subsection_revision_reaches_export(tmp_path: Path) -> None:
    """A level-3 subsection revision must land in the exported Markdown."""
    proj = _finalized_project(tmp_path)
    _write(
        proj,
        ANCHOR_L3_LOGIN,
        f"### {ANCHOR_L3_LOGIN}\n\n[REV] 修订后的登录能力描述。\n\n{AC_LOGIN_BLOCK}",
    )
    result = _finalize(proj)
    assert result.blocked == [] and not result.errors
    assert "[REV] 修订后的登录能力描述。" in _prd_path(proj).read_text(encoding="utf-8")


def test_deep_revision_updates_all_ancestor_bodies(tmp_path: Path) -> None:
    """A level-4 write must update its own node and every ancestor tile body."""
    proj = _finalized_project(tmp_path)
    _write(proj, ANCHOR_L4_AC_LOGIN, f"#### {ANCHOR_L4_AC_LOGIN}\n\n[REV-AC] 断言已修订。")
    for anchor in (ANCHOR_L4_AC_LOGIN, ANCHOR_L3_LOGIN, ANCHOR_L2_FEATURES):
        body = _section_body(proj, anchor)
        assert body is not None and "[REV-AC] 断言已修订。" in body, anchor


def test_level2_revision_resyncs_child_nodes(tmp_path: Path) -> None:
    """Rewriting a level-2 tile must refresh the child section nodes it embeds."""
    proj = _finalized_project(tmp_path)
    _write(
        proj,
        ANCHOR_L2_FEATURES,
        (
            f"## {ANCHOR_L2_FEATURES}\n"
            "\n"
            f"### {ANCHOR_L3_LOGIN}\n"
            "\n"
            "[CHILD-REV] 修订后的登录能力描述。\n"
            "\n"
            f"{AC_LOGIN_BLOCK}\n"
            "\n"
            f"### {ANCHOR_L3_LOGOUT}\n"
            "\n"
            "允许已登录用户终止当前会话，清空客户端 token。\n"
            "\n"
            f"#### {ANCHOR_L4_AC_LOGOUT}\n"
            "\n"
            "调用 logout 接口返回 204；客户端本地 token 被擦除。"
        ),
    )
    child = _section_body(proj, ANCHOR_L3_LOGIN)
    assert child is not None and "[CHILD-REV] 修订后的登录能力描述。" in child


def test_level2_revision_drops_removed_child_nodes(tmp_path: Path) -> None:
    """Child sections absent from the rewritten level-2 body must be deleted."""
    proj = _finalized_project(tmp_path)
    _write(
        proj,
        ANCHOR_L2_FEATURES,
        (
            f"## {ANCHOR_L2_FEATURES}\n"
            "\n"
            f"### {ANCHOR_L3_LOGIN}\n"
            "\n"
            "允许已注册用户用邮箱 + 密码完成身份认证。\n"
            "\n"
            f"{AC_LOGIN_BLOCK}"
        ),
    )
    assert _section_body(proj, ANCHOR_L3_LOGOUT) is None
    assert _section_body(proj, ANCHOR_L4_AC_LOGOUT) is None
    _finalize(proj)
    assert ANCHOR_L3_LOGOUT not in _prd_path(proj).read_text(encoding="utf-8")


def test_narrative_write_preserves_contains_entity_edges(tmp_path: Path) -> None:
    """Re-narrating a section must not silently drop its contains_entity edges."""
    proj = _finalized_project(tmp_path)
    assert "F-001" in _contained_entity_ids(proj, ANCHOR_L3_LOGIN), (
        "fixture precondition: the login section owns F-001"
    )
    _write(
        proj,
        ANCHOR_L3_LOGIN,
        f"### {ANCHOR_L3_LOGIN}\n\n[REV] 修订后的登录能力描述。\n\n{AC_LOGIN_BLOCK}",
    )
    assert "F-001" in _contained_entity_ids(proj, ANCHOR_L3_LOGIN)


def test_new_deep_anchor_rejected(tmp_path: Path) -> None:
    """A brand-new level>=3 anchor has no tile to land in — explicit error."""
    proj = _finalized_project(tmp_path)
    with pytest.raises(KGValidationError, match="§2.9"):
        _write(proj, "§2.9 新增子节", "### §2.9 新增子节\n\n凭空的深层子节。")


def test_new_level2_anchor_still_appends(tmp_path: Path) -> None:
    """Appending a new level-2 chapter stays a legal, exported operation."""
    proj = _finalized_project(tmp_path)
    _write(proj, "§9 附录", "附录正文。")
    _finalize(proj)
    text = _prd_path(proj).read_text(encoding="utf-8")
    assert "## §9 附录" in text
    assert text.index(ANCHOR_L2_FEATURES) < text.index("§9 附录")


def test_transact_write_narrative_cascades(tmp_path: Path) -> None:
    """The transact write_narrative op must run the same cascade."""
    proj = _finalized_project(tmp_path)
    cw.transact(
        str(proj),
        {
            "operations": [
                {
                    "op": "write_narrative",
                    "doc_id": "prd",
                    "anchor": ANCHOR_L3_LOGIN,
                    "narrative": (
                        f"### {ANCHOR_L3_LOGIN}\n\n[TXN-REV] 事务修订。\n\n{AC_LOGIN_BLOCK}"
                    ),
                }
            ]
        },
    )
    gc.collect()
    invalidate_cache()
    result = _finalize(proj)
    assert result.blocked == [] and not result.errors
    assert "[TXN-REV] 事务修订。" in _prd_path(proj).read_text(encoding="utf-8")


# --- P-5 end-to-end regression (downstream Ink-Source replay) -----------------


def test_scattered_multilevel_revisions_all_reach_export(tmp_path: Path) -> None:
    """>=5 scattered revisions across heading depths must ALL reach the export.

    Replays the downstream failure shape: several narrative revisions spread
    over level-2/3/4 sections of one document, then one finalize.
    Every revision must appear in the exported Markdown (non-empty diff,
    changed content hash) and reconcile must settle in_sync.
    """
    proj = _finalized_project(tmp_path)
    before = _prd_path(proj).read_bytes()

    _write(proj, ANCHOR_L2_OVERVIEW, f"## {ANCHOR_L2_OVERVIEW}\n\n[REV-1] scope 已修订。")
    _write(
        proj,
        ANCHOR_L3_LOGIN,
        f"### {ANCHOR_L3_LOGIN}\n\n[REV-2] 登录描述已修订。\n\n{AC_LOGIN_BLOCK}",
    )
    _write(proj, ANCHOR_L4_AC_LOGIN, f"#### {ANCHOR_L4_AC_LOGIN}\n\n[REV-3] 登录 AC 已修订。")
    _write(
        proj,
        ANCHOR_L3_LOGOUT,
        (
            f"### {ANCHOR_L3_LOGOUT}\n"
            "\n"
            "[REV-4] 登出描述已修订。\n"
            "\n"
            f"#### {ANCHOR_L4_AC_LOGOUT}\n"
            "\n"
            "调用 logout 接口返回 204；客户端本地 token 被擦除。"
        ),
    )
    _write(proj, ANCHOR_L4_AC_LOGOUT, f"#### {ANCHOR_L4_AC_LOGOUT}\n\n[REV-5] 登出 AC 已修订。")

    result = _finalize(proj)
    assert result.blocked == [] and not result.errors

    after = _prd_path(proj).read_bytes()
    text = after.decode("utf-8")
    for marker in ("[REV-1]", "[REV-2]", "[REV-3]", "[REV-4]", "[REV-5]"):
        assert marker in text, f"revision {marker} was silently lost on export"
    assert hashlib.sha256(before).hexdigest() != hashlib.sha256(after).hexdigest()

    report = _reconcile(proj)
    assert _state_for(report, PRD) == "in_sync"


# --- narrative sub-entity sync: the revision path must not drift the graph ----


def _entity_exists(proj: Path, iri_tail: str) -> bool:
    with KnowledgeGraph.connect(_config(proj)) as kg:
        return bool(kg.store.query(f"ASK {{ <https://cataforge.dev/instance/{iri_tail}> ?p ?o }}"))


def _entity_narrative(proj: Path, iri_tail: str) -> str | None:
    with KnowledgeGraph.connect(_config(proj)) as kg:
        ns = kg.config.ontology_namespace.rstrip("/") + "/"
        rows = list(
            kg.store.query(
                f"SELECT ?body WHERE {{ "
                f"<https://cataforge.dev/instance/{iri_tail}> <{ns}narrative_body> ?body }}"
            )
        )
        return str(rows[0]["body"].value) if rows else None


def test_narrative_new_ac_creates_subentity(tmp_path: Path) -> None:
    """An AC added by a narrative revision must land as a KG sub-entity."""
    proj = _finalized_project(tmp_path)
    _write(
        proj,
        ANCHOR_L3_LOGIN,
        (
            f"### {ANCHOR_L3_LOGIN}\n"
            "\n"
            "允许已注册用户用邮箱 + 密码完成身份认证。\n"
            "\n"
            "- AC-003: 连续失败 5 次锁定账户 15 分钟。\n"
            "\n"
            f"{AC_LOGIN_BLOCK}"
        ),
    )
    assert _entity_exists(proj, "F-001/AC-003"), (
        "narrative-added AC must be extracted into the graph"
    )
    with KnowledgeGraph.connect(_config(proj)) as kg:
        ns = kg.config.ontology_namespace.rstrip("/") + "/"
        assert kg.store.query(
            "ASK { <https://cataforge.dev/instance/F-001/AC-003> "
            f"<{ns}part_of> <https://cataforge.dev/instance/F-001> }}"
        )


def test_narrative_changed_ac_updates_subentity(tmp_path: Path) -> None:
    """Rewriting an AC's text must refresh the AC entity, not just the section."""
    proj = _finalized_project(tmp_path)
    _write(
        proj,
        ANCHOR_L4_AC_LOGIN,
        f"#### {ANCHOR_L4_AC_LOGIN}\n\n[AC-REV] 输入合法凭据返回 201 + JWT。",
    )
    body = _entity_narrative(proj, "F-001/AC-001")
    assert body is not None and "[AC-REV]" in body, (
        "narrative AC revision must reach the AC entity node"
    )


def test_narrative_removed_ac_deletes_subentity(tmp_path: Path) -> None:
    """An AC dropped from the rewritten section must leave the graph."""
    proj = _finalized_project(tmp_path)
    _write(proj, ANCHOR_L3_LOGIN, f"### {ANCHOR_L3_LOGIN}\n\n[REV] 移除 AC 的修订描述。")
    assert not _entity_exists(proj, "F-001/AC-001")


def _implements_edge_present(proj: Path) -> bool:
    """Connection scoped to its own frame so the RocksDB lock frees on gc."""
    edge = (
        "ASK { <https://cataforge.dev/instance/M-001> "
        "<https://cataforge.dev/ontology/implements> "
        "<https://cataforge.dev/instance/F-001> }"
    )
    with KnowledgeGraph.connect(_config(proj)) as kg:
        return bool(kg.store.query(edge))


def test_narrative_rewrite_preserves_entity_outgoing_edges(tmp_path: Path) -> None:
    """A narrative rewrite that changes an entity's body must keep its edges."""
    proj = _finalized_project(tmp_path)
    assert _implements_edge_present(proj), "fixture precondition: M-001 implements F-001"
    gc.collect()
    invalidate_cache()
    cw.write_narrative(
        str(proj),
        doc_id="arch",
        anchor="§2.1 M-001 认证模块",
        narrative=(
            "### §2.1 M-001 认证模块\n\n- 映射功能: prd#§2.F-001\n- [REV] 增补认证模块职责描述。"
        ),
    )
    gc.collect()
    invalidate_cache()
    assert _implements_edge_present(proj), "narrative rewrite dropped the entity's outgoing edge"


def test_reconcile_ok_after_narrative_ac_addition(tmp_path: Path) -> None:
    """The fixed revision path leaves no graph-internal entity drift behind."""
    proj = _finalized_project(tmp_path)
    _write(
        proj,
        ANCHOR_L3_LOGIN,
        (
            f"### {ANCHOR_L3_LOGIN}\n"
            "\n"
            "允许已注册用户用邮箱 + 密码完成身份认证。\n"
            "\n"
            "- AC-003: 连续失败 5 次锁定账户 15 分钟。\n"
            "\n"
            f"{AC_LOGIN_BLOCK}"
        ),
    )
    _finalize(proj)
    report = _reconcile(proj)
    record = _record_for(report, PRD)
    assert record.unabsorbed_entities == []
    assert report.ok


# --- reconcile probe: graph-internal tile-cover violations ---------------------


def _record_for(report, rel_tail: tuple[str, ...]):
    suffix = "/".join(rel_tail)
    matches = [d for d in report.documents if d.source_path.replace("\\", "/").endswith(suffix)]
    assert matches, f"no DocumentDriftRecord ending in {suffix!r}"
    return matches[0]


def _desync_login_section(proj: Path) -> None:
    """Rewrite one child node without its tile — the legacy single-copy write.

    Connection lives inside this frame so the RocksDB lock is actually freed
    by the gc.collect() that follows (Windows single-process behavior).
    """
    with KnowledgeGraph.connect(_config(proj)) as kg, kg.transaction() as txn:
        body = f"### {ANCHOR_L3_LOGIN}\n\n[ORPHANED-REV] 只写了子节点的修订。"
        txn.add_section(
            "prd",
            ANCHOR_L3_LOGIN,
            body,
            hashlib.sha256(body.encode("utf-8")).hexdigest(),
            title=ANCHOR_L3_LOGIN,
        )


def test_reconcile_flags_desynced_tile_sections(tmp_path: Path) -> None:
    """A section node diverging from its tile (legacy single-copy write) must
    fail the gate even when the document triages in_sync."""
    proj = _finalized_project(tmp_path)
    _desync_login_section(proj)
    gc.collect()
    invalidate_cache()

    report = _reconcile(proj)
    record = _record_for(report, PRD)
    assert ANCHOR_L3_LOGIN in record.desynced_sections
    assert record.remediation == "manual"
    assert not report.ok
    assert "desynced" in report.gate_summary


def _plant_unabsorbed_ac(proj: Path) -> None:
    """Write an AC into section bodies without its entity (tile-cover consistent).

    Reproduces a text-only revision writer: both the level-2 tile and the child
    node carry the new bullet, so the desync probe stays green while the
    section text and the sub-entity set diverge.
    """
    child_body = (
        f"### {ANCHOR_L3_LOGIN}\n"
        "\n"
        "允许已注册用户用邮箱 + 密码完成身份认证。\n"
        "\n"
        "- AC-009: 未入图的新增断言。\n"
        "\n"
        f"{AC_LOGIN_BLOCK}"
    )
    tile_body = (
        f"## {ANCHOR_L2_FEATURES}\n"
        "\n"
        f"{child_body}\n"
        "\n"
        f"### {ANCHOR_L3_LOGOUT}\n"
        "\n"
        "允许已登录用户终止当前会话，清空客户端 token。\n"
        "\n"
        f"#### {ANCHOR_L4_AC_LOGOUT}\n"
        "\n"
        "调用 logout 接口返回 204；客户端本地 token 被擦除。"
    )
    with KnowledgeGraph.connect(_config(proj)) as kg, kg.transaction() as txn:
        txn.add_section(
            "prd",
            ANCHOR_L2_FEATURES,
            tile_body,
            hashlib.sha256(tile_body.encode("utf-8")).hexdigest(),
            title=ANCHOR_L2_FEATURES,
        )
        txn.add_section(
            "prd",
            ANCHOR_L3_LOGIN,
            child_body,
            hashlib.sha256(child_body.encode("utf-8")).hexdigest(),
            title=ANCHOR_L3_LOGIN,
        )


def test_reconcile_flags_unabsorbed_section_entities(tmp_path: Path) -> None:
    """Section text defining an entity the graph lacks must fail the gate."""
    proj = _finalized_project(tmp_path)
    _plant_unabsorbed_ac(proj)
    gc.collect()
    invalidate_cache()

    report = _reconcile(proj)
    record = _record_for(report, PRD)
    assert record.desynced_sections == [], "precondition: the plant keeps tile-cover intact"
    assert "F-001/AC-009" in record.unabsorbed_entities
    assert record.remediation != "none"
    assert not report.ok
    assert "unabsorbed" in report.gate_summary


def test_reconcile_clean_after_cascade_write(tmp_path: Path) -> None:
    """Cascade writes leave no tile-cover violation behind."""
    proj = _finalized_project(tmp_path)
    _write(
        proj,
        ANCHOR_L3_LOGIN,
        f"### {ANCHOR_L3_LOGIN}\n\n[REV] 修订后的登录能力描述。\n\n{AC_LOGIN_BLOCK}",
    )
    _finalize(proj)
    report = _reconcile(proj)
    record = _record_for(report, PRD)
    assert record.desynced_sections == []
    assert report.ok
