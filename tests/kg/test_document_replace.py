"""Whole-document replace semantics on the ingest write path.

An approved Document's content is frozen against ingest absorbs (the file
roundtrip echoes `status: approved` verbatim, so the frontmatter carries no
deliberate intent — unlike an explicit re-author). Entity home slots
(`cf:source_doc` / `cf:source_section`) follow the entity even when its
content hash is unchanged, so a definition moved across documents keeps
trace queries truthful.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.domain.kg import KGConfig, init_store
from cataforge.domain.kg._errors import KGValidationError
from cataforge.domain.kg.ingest import run_migration


def _write(project_root: Path, doc_type: str, name: str, body: str) -> None:
    d = project_root / "docs" / doc_type
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def _one_value(store, sparql: str) -> str | None:
    for row in store.query(sparql):
        return str(row[0].value) if row[0] is not None else None
    return None


_NS = "PREFIX cf: <https://cataforge.dev/ontology/> "

_APPROVED_PRD = (
    "---\nid: prd\ndoc_type: prd\nstatus: approved\n---\n"
    "# PRD\n\n## §1 功能\n\n### F-001 登录\n\n登录功能已冻结。\n"
)


def _prd_content_hash(store) -> str | None:
    return _one_value(
        store,
        _NS + 'SELECT ?h WHERE { ?d a cf:Document ; cf:source_doc "prd" ; cf:content_hash ?h }',
    )


def test_ingest_refuses_content_change_to_approved_document(tmp_path: Path) -> None:
    _write(tmp_path, "prd", "prd.md", _APPROVED_PRD)
    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, tmp_path, config, doc_types=("prd",))
    frozen_hash = _prd_content_hash(handle.raw)
    assert frozen_hash is not None

    _write(tmp_path, "prd", "prd.md", _APPROVED_PRD.replace("已冻结", "被篡改"))

    with pytest.raises(KGValidationError, match="approved"):
        run_migration(handle.raw, tmp_path, config, doc_types=("prd",))

    assert _prd_content_hash(handle.raw) == frozen_hash
    body = _one_value(
        handle.raw,
        _NS + 'SELECT ?b WHERE { ?s a cf:Section ; cf:source_doc "prd" ; cf:narrative_body ?b '
        'FILTER(CONTAINS(?b, "登录功能")) }',
    )
    assert body is not None and "已冻结" in body


def test_ingest_allows_identical_reingest_of_approved(tmp_path: Path) -> None:
    _write(tmp_path, "prd", "prd.md", _APPROVED_PRD)
    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, tmp_path, config, doc_types=("prd",))

    stats, _e, _r = run_migration(handle.raw, tmp_path, config, doc_types=("prd",))

    assert stats.structure_stats.documents_skipped == 1


def test_reingest_syncs_unchanged_subordinate_source_section(tmp_path: Path) -> None:
    # AC-001's hash covers only its own bullet line; renaming the owning
    # feature heading leaves the hash unchanged, so a plain upsert would skip
    # it and leave `cf:source_section` pointing at the old heading.
    doc = (
        "---\nid: prd\ndoc_type: prd\n---\n# PRD\n\n## §1 功能\n\n"
        "### F-001 登录\n\n- AC-001: 邮箱密码可登录\n"
    )
    _write(tmp_path, "prd", "prd.md", doc)
    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, tmp_path, config, doc_types=("prd",))

    section_query = _NS + 'SELECT ?sec WHERE { ?s cf:entity_id "AC-001" ; cf:source_section ?sec }'
    assert _one_value(handle.raw, section_query) == "F-001 登录"

    _write(tmp_path, "prd", "prd.md", doc.replace("### F-001 登录", "### F-001 用户登录"))
    run_migration(handle.raw, tmp_path, config, doc_types=("prd",))

    assert _one_value(handle.raw, section_query) == "F-001 用户登录"


def test_failed_repair_reverts_applied_home_sync(tmp_path: Path, monkeypatch) -> None:
    # A hash-skip home sync applied by an earlier write in the repair batch
    # must not survive when a later write fails and the batch compensates.
    import cataforge.domain.kg.repair as repair_mod

    doc = (
        "---\nid: prd\ndoc_type: prd\n---\n# PRD\n\n## §1 功能\n\n"
        "### F-001 登录\n\n- AC-001: 邮箱密码可登录\n"
    )
    _write(tmp_path, "prd", "prd.md", doc)
    config = KGConfig(store_backend="memory", kg_active_doc_types={"prd"})
    handle = init_store(config, force=True)
    run_migration(handle.raw, tmp_path, config, doc_types=("prd",))

    section_query = _NS + 'SELECT ?sec WHERE { ?s cf:entity_id "AC-001" ; cf:source_section ?sec }'
    assert _one_value(handle.raw, section_query) == "F-001 登录"

    # The heading rename leaves AC-001's hash unchanged (home-sync path) while
    # the changed sections give repair something to reingest.
    _write(tmp_path, "prd", "prd.md", doc.replace("### F-001 登录", "### F-001 用户登录"))

    def _boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError("injected structure-write failure")

    monkeypatch.setattr(repair_mod, "write_structure", _boom)
    stats = repair_mod.repair(handle.raw, tmp_path, config)

    assert any("injected structure-write failure" in e for e in stats.errors), stats.errors
    assert _one_value(handle.raw, section_query) == "F-001 登录"


def test_entity_home_sync_quads_rehomes_source_doc(tmp_path: Path) -> None:
    from cataforge.domain.kg._quads import entity_home_sync_quads
    from cataforge.domain.kg.ingest.iri import entity_iri

    _write(
        tmp_path,
        "prd",
        "prd.md",
        "---\nid: prd\ndoc_type: prd\n---\n# PRD\n\n## §1 功能\n\n### F-001 登录\n\n登录。\n",
    )
    config = KGConfig(store_backend="memory")
    handle = init_store(config, force=True)
    run_migration(handle.raw, tmp_path, config, doc_types=("prd",))
    iri = entity_iri("F-001", config.base_namespace)
    namespace = config.ontology_namespace.rstrip("/") + "/"

    removes, adds = entity_home_sync_quads(
        handle.raw, iri, "arch", "F-001 登录", namespace=namespace
    )
    for q in removes:
        handle.raw.remove(q)
    for q in adds:
        handle.raw.add(q)

    src_query = _NS + 'SELECT ?src WHERE { ?s cf:entity_id "F-001" ; cf:source_doc ?src }'
    assert _one_value(handle.raw, src_query) == "arch"

    # Idempotent: a second sync against the now-current home stages nothing.
    removes, adds = entity_home_sync_quads(
        handle.raw, iri, "arch", "F-001 登录", namespace=namespace
    )
    assert removes == [] and adds == []
