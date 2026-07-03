"""Finalize export scope, overwrite guard, dry-run plan, and the reconcile
enrichment / remediation-direction signals they feed."""

from __future__ import annotations

import gc
import json
from pathlib import Path

import pytest

from cataforge.domain.kg import KnowledgeGraph
from cataforge.domain.kg._dispatch import invalidate_cache
from cataforge.domain.kg.authority import (
    DRIFT_GRAPH_AHEAD,
    DRIFT_IN_SYNC,
    DRIFT_NEVER_EXPORTED,
    REMEDIATE_EXPORT,
    REMEDIATE_INGEST,
)
from tests.kg.test_reconcile_triage import (
    PRD,
    _config,
    _document_baseline,
    _ingest_only_project,
    _reconcile,
    _rewrite_a_section_body,
    _state_for,
)

pytestmark = pytest.mark.usefixtures("_isolate_cache")


@pytest.fixture
def _isolate_cache():
    invalidate_cache()
    yield
    invalidate_cache()


def _set_graph_mode(proj: Path) -> None:
    fw = proj / ".cataforge" / "framework.json"
    data = json.loads(fw.read_text(encoding="utf-8"))
    data.setdefault("context", {})["mode"] = "graph"
    fw.write_text(json.dumps(data), encoding="utf-8")
    invalidate_cache()


def _graph_project(tmp_path: Path) -> Path:
    proj = _ingest_only_project(tmp_path)
    _set_graph_mode(proj)
    return proj


def _finalize(proj: Path, **kwargs):
    from cataforge.application.context import write as ctx_write

    result = ctx_write.finalize(str(proj), **kwargs)
    gc.collect()
    invalidate_cache()
    return result


def _append_semantic_section(path: Path) -> None:
    path.write_text(
        path.read_text(encoding="utf-8") + "\n## §9 追加需求\n\n仅存在于 Markdown 的新内容。\n",
        encoding="utf-8",
    )


def _author_edge(proj: Path, subject_id: str, predicate: str, object_id: str) -> None:
    """Write one traceability edge directly into the graph (no Markdown form).

    Connection lives inside this frame so the RocksDB lock is actually freed
    by the gc.collect() that follows (Windows single-process behavior).
    """
    with KnowledgeGraph.connect(_config(proj)) as kg, kg.transaction() as txn:
        txn.add_relation(subject_id, predicate, object_id)


def _first_prd_anchor(proj: Path) -> str:
    with KnowledgeGraph.connect(_config(proj)) as kg:
        ns = kg.config.ontology_namespace.rstrip("/") + "/"
        rows = list(
            kg.store.query(
                f"PREFIX cf: <{ns}> "
                'SELECT ?anchor WHERE { ?s a cf:Section ; cf:source_doc "prd" ; '
                'cf:section_anchor ?anchor ; cf:section_level "2" } ORDER BY ?anchor LIMIT 1'
            )
        )
        assert rows, "fixture prd must carry a level-2 section"
        return str(rows[0]["anchor"].value)


# --- overwrite guard ----------------------------------------------------------


def test_ingest_then_finalize_passes_without_force(tmp_path: Path) -> None:
    """The canonical ingest → finalize flow needs no --force and seeds baselines."""
    proj = _graph_project(tmp_path)
    result = _finalize(proj)
    assert result.blocked == []
    assert not result.errors
    report = _reconcile(proj)
    for d in report.documents:
        assert d.state == DRIFT_IN_SYNC, (d.source_path, d.state)


def test_finalize_blocks_stale_graph_overwrite(tmp_path: Path) -> None:
    """Markdown content the graph never absorbed must not be overwritten."""
    proj = _graph_project(tmp_path)
    prd = proj.joinpath(*PRD)
    _append_semantic_section(prd)
    before = prd.read_bytes()

    result = _finalize(proj)
    blocked_norm = [p.replace("\\", "/") for p in result.blocked]
    assert any(p.endswith("prd-vertical-slice.md") for p in blocked_norm), result.plan
    assert prd.read_bytes() == before
    assert _document_baseline(proj, PRD) is None, "a blocked file must not gain a baseline"


def test_finalize_force_overwrites_and_backs_up(tmp_path: Path) -> None:
    proj = _graph_project(tmp_path)
    prd = proj.joinpath(*PRD)
    _append_semantic_section(prd)
    edited = prd.read_text(encoding="utf-8")

    result = _finalize(proj, force=True)
    assert result.blocked == []
    assert "§9 追加需求" not in prd.read_text(encoding="utf-8")

    backups_root = proj / ".cataforge" / ".backups"
    backup_copies = list(backups_root.glob("finalize-*/prd/prd-vertical-slice.md"))
    assert backup_copies, f"no backup written under {backups_root}"
    assert backup_copies[0].read_text(encoding="utf-8") == edited


def test_finalize_graph_ahead_still_exports_without_force(tmp_path: Path) -> None:
    """A file untouched since its last export follows the graph freely."""
    proj = _graph_project(tmp_path)
    _finalize(proj)
    _rewrite_a_section_body(proj, " [graph edit]")

    result = _finalize(proj)
    assert result.blocked == []
    assert "[graph edit]" in proj.joinpath(*PRD).read_text(encoding="utf-8")


# --- scope + dry-run ------------------------------------------------------------


def test_finalize_doc_type_scope_leaves_other_types_untouched(tmp_path: Path) -> None:
    proj = _graph_project(tmp_path)
    _finalize(proj)
    _rewrite_a_section_body(proj, " [graph edit]")

    result = _finalize(proj, doc_types=["arch"])
    assert all(p.replace("\\", "/").startswith("docs/arch") for p, _ in result.plan), result.plan
    assert "[graph edit]" not in proj.joinpath(*PRD).read_text(encoding="utf-8")

    _finalize(proj, doc_types=["prd"])
    assert "[graph edit]" in proj.joinpath(*PRD).read_text(encoding="utf-8")


def test_finalize_dry_run_writes_nothing(tmp_path: Path) -> None:
    proj = _graph_project(tmp_path)
    before = proj.joinpath(*PRD).read_bytes()

    result = _finalize(proj, dry_run=True)
    assert result.plan, "dry-run must report a per-document plan"
    assert result.file_records == []
    assert proj.joinpath(*PRD).read_bytes() == before
    assert _document_baseline(proj, PRD) is None, "dry-run must not seed baselines"
    assert _state_for(_reconcile(proj), PRD) == DRIFT_NEVER_EXPORTED


# --- reconcile: remediation direction + enrichment ------------------------------


def test_never_exported_remediation_follows_content_direction(tmp_path: Path) -> None:
    proj = _graph_project(tmp_path)

    balanced = _reconcile(proj)
    assert _state_for(balanced, PRD) == DRIFT_NEVER_EXPORTED
    prd_record = next(d for d in balanced.documents if d.source_path.endswith(PRD[-1]))
    assert prd_record.remediation == REMEDIATE_EXPORT

    _append_semantic_section(proj.joinpath(*PRD))
    md_ahead = _reconcile(proj)
    prd_record = next(d for d in md_ahead.documents if d.source_path.endswith(PRD[-1]))
    assert prd_record.remediation == REMEDIATE_INGEST


def test_write_narrative_stamps_baseline_and_unblocks_export(tmp_path: Path) -> None:
    """Graph-side authoring absorbs the current disk state: the pending export
    triages as graph_ahead and finalize needs no --force."""
    from cataforge.application.context import write as ctx_write

    proj = _graph_project(tmp_path)
    anchor = _first_prd_anchor(proj)
    gc.collect()
    invalidate_cache()

    ctx_write.write_narrative(str(proj), doc_id="prd", anchor=anchor, narrative="改写后的正文。")
    gc.collect()
    invalidate_cache()

    assert _state_for(_reconcile(proj), PRD) == DRIFT_GRAPH_AHEAD

    result = _finalize(proj)
    assert result.blocked == []
    assert "改写后的正文" in proj.joinpath(*PRD).read_text(encoding="utf-8")


def test_direct_authored_edge_is_enrichment_not_ghost(tmp_path: Path) -> None:
    """A KG-only edge on a content-synced document is enrichment, not drift."""
    proj = _graph_project(tmp_path)
    _finalize(proj)

    _author_edge(proj, "F-001", "cf:depends_on", "F-002")
    gc.collect()
    invalidate_cache()

    report = _reconcile(proj)
    prd_report = report.per_doc_type["prd"]
    assert ("F-001", "cf:depends_on", "F-002") in prd_report.enrichment_relations
    assert ("F-001", "cf:depends_on", "F-002") not in prd_report.ghost_relations
    assert prd_report.divergence_count == 0
    assert report.enrichment_count == 1
    assert report.ok is True

    payload = report.to_dict()
    assert payload["enrichment_count"] == 1
    assert payload["per_doc_type"]["prd"]["enrichment_relations"] == [
        ["F-001", "cf:depends_on", "F-002"]
    ]


def test_edge_on_drifted_document_stays_ghost(tmp_path: Path) -> None:
    """Once the home document drifts, a KG-only edge is drift again."""
    proj = _graph_project(tmp_path)
    _finalize(proj)

    _author_edge(proj, "F-001", "cf:depends_on", "F-002")
    gc.collect()
    invalidate_cache()

    _append_semantic_section(proj.joinpath(*PRD))
    report = _reconcile(proj)
    prd_report = report.per_doc_type["prd"]
    assert ("F-001", "cf:depends_on", "F-002") in prd_report.ghost_relations
    assert prd_report.enrichment_relations == []
