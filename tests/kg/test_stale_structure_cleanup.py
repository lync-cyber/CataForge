"""Re-ingest must not resurrect deleted sections or keep renamed Document ghosts.

A document whose markdown folded away a chapter (or renamed its frontmatter
doc_id) previously left the old Section / Document nodes in the graph forever:
``write_structure`` only upserts by IRI. The stale nodes then leak back into
``render_document`` (whole chapters regrow on export) and show up as ghost
drift in reconcile.
"""

from __future__ import annotations

import shutil
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"

_PRD_REL = Path("docs") / "prd" / "prd-vertical-slice.md"

_EXTRA_SECTION = "\n## §3 历史记录\n\n一段将被折叠删除的历史正文。\n"


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    shutil.copytree(FIXTURE_ROOT / "waterfall", proj)
    return proj


def _store():
    from cataforge.domain.kg import KGConfig, init_store

    config = KGConfig(store_backend="memory")
    return init_store(config, force=True), config


def _migrate(handle, config, proj: Path):
    from cataforge.domain.kg.ingest import run_migration

    return run_migration(handle.raw, proj, config)


def _render(handle, config, source_rel: Path) -> str:
    from cataforge.domain.kg._quads import cf_namespace
    from cataforge.domain.kg.export.document_pipeline import _list_documents, render_document

    ns = cf_namespace(config)
    for doc in _list_documents(handle.raw, ns):
        if Path(doc["source_path"]) == source_rel:
            return render_document(handle.raw, ns, doc)
    raise AssertionError(f"no Document with source_path {source_rel}")


def test_deleted_section_does_not_resurrect_in_render(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    prd = proj / _PRD_REL
    prd.write_text(prd.read_text(encoding="utf-8") + _EXTRA_SECTION, encoding="utf-8")

    handle, config = _store()
    _migrate(handle, config, proj)
    assert "历史记录" in _render(handle, config, _PRD_REL)

    # Fold the chapter away on disk, re-ingest: the graph render must follow.
    text = prd.read_text(encoding="utf-8")
    prd.write_text(text[: text.index("\n## §3 历史记录")] + "\n", encoding="utf-8")
    _migrate(handle, config, proj)

    rendered = _render(handle, config, _PRD_REL)
    assert "历史记录" not in rendered, "stale Section resurrected in render"


def test_deleted_section_leaves_no_ghost_drift(tmp_path: Path) -> None:
    from cataforge.domain.kg.reconcile import reconcile

    proj = _project(tmp_path)
    prd = proj / _PRD_REL
    prd.write_text(prd.read_text(encoding="utf-8") + _EXTRA_SECTION, encoding="utf-8")

    handle, config = _store()
    _migrate(handle, config, proj)
    text = prd.read_text(encoding="utf-8")
    prd.write_text(text[: text.index("\n## §3 历史记录")] + "\n", encoding="utf-8")
    _migrate(handle, config, proj)

    report = reconcile(handle.raw, proj, config)
    for per in report.per_doc_type.values():
        assert per.ghost_sections == [], per.to_dict()


def test_renamed_doc_id_leaves_single_document_node(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    prd = proj / _PRD_REL

    handle, config = _store()
    _migrate(handle, config, proj)

    # Rename the frontmatter doc_id: the Document IRI changes, and the node
    # under the old IRI (same source_path) must be cleaned up, not kept as a
    # ghost twin pointing at the same physical file.
    prd.write_text(
        prd.read_text(encoding="utf-8").replace("doc_id: prd\n", "doc_id: prd-renamed\n"),
        encoding="utf-8",
    )
    _migrate(handle, config, proj)

    from cataforge.domain.kg._quads import cf_namespace
    from cataforge.domain.kg.export.document_pipeline import _list_documents

    ns = cf_namespace(config)
    same_path = [d for d in _list_documents(handle.raw, ns) if Path(d["source_path"]) == _PRD_REL]
    assert len(same_path) == 1, [d["doc_iri"] for d in same_path]
    assert same_path[0]["doc_iri"].endswith("prd-renamed")

    # The ghost's sections must be gone too — they'd otherwise stay reachable
    # to section-level queries forever.
    from cataforge.domain.kg._sparql_utils import select_rows

    old_iri = next(
        (d["doc_iri"] for d in same_path if not d["doc_iri"].endswith("prd-renamed")), None
    )
    assert old_iri is None
    rows = list(
        select_rows(
            handle.raw,
            f"PREFIX cf: <{ns}> SELECT ?s WHERE {{ ?s a cf:Section ; "
            "cf:part_of_document ?d . ?d cf:source_path ?p . "
            f'FILTER(STR(?p) = "{_PRD_REL.as_posix()}") }}',
        )
    )
    # Sections exist only for the live document node.
    assert rows, "renamed document lost its sections entirely"
