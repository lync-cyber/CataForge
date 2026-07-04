"""Document-level three-way drift triage layered onto reconcile.

The id-set diff (`overall_divergence_count` / `ok`) and the content triage
(`documents` / `document_drift_count`) are orthogonal: the triage tests assert
the new content states without perturbing the legacy id-diff counts.
"""

from __future__ import annotations

import gc
import hashlib
import json
from pathlib import Path

import pytest

from cataforge.domain.kg import KGConfig, KnowledgeGraph, KnowledgeGraphStore, init_store
from cataforge.domain.kg._dispatch import invalidate_cache, kg_config_for
from cataforge.domain.kg.export.document_pipeline import EXPORTED_CONTENT_HASH_SLOT
from cataforge.domain.kg.reconcile import (
    DRIFT_CONFLICT,
    DRIFT_GRAPH_AHEAD,
    DRIFT_HUMAN_EDIT,
    DRIFT_IN_SYNC,
    DRIFT_NEVER_EXPORTED,
    DocumentDriftRecord,
    PerDocTypeReport,
    ReconcileReport,
    reconcile,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"

PRD = ("docs", "prd", "prd-vertical-slice.md")


@pytest.fixture(autouse=True)
def _isolate_cache():
    invalidate_cache()
    yield
    invalidate_cache()


def _ingest_only_project(tmp_path: Path) -> Path:
    """Copy the fixture and migrate its docs into an on-disk store (no export)."""
    import shutil

    from cataforge.domain.kg.ingest import run_migration

    proj = tmp_path / "proj"
    shutil.copytree(FIXTURE_ROOT / "waterfall", proj)
    cfg = kg_config_for(proj)
    handle = init_store(cfg, force=True)
    run_migration(handle.raw, proj, cfg)
    del handle
    gc.collect()
    invalidate_cache()
    return proj


def _finalized_project(tmp_path: Path) -> Path:
    """An ingest-only project that has also had one finalize (export) pass.

    finalize only exports (graph → md) under graph authoring, so the fixture's
    framework.json declares it before 定稿; the export then writes the
    ``cf:exported_content_hash`` baseline the triage states key off.
    """
    from cataforge.application.context import write as ctx_write

    proj = _ingest_only_project(tmp_path)
    fw = proj / ".cataforge" / "framework.json"
    data = json.loads(fw.read_text(encoding="utf-8"))
    data.setdefault("context", {})["mode"] = "graph"
    fw.write_text(json.dumps(data), encoding="utf-8")
    invalidate_cache()
    ctx_write.finalize(str(proj))
    gc.collect()
    invalidate_cache()
    return proj


def _config(proj: Path) -> KGConfig:
    return KGConfig(
        store_backend="oxigraph",
        db_path=proj / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )


def _reconcile(proj: Path) -> object:
    cfg = _config(proj)
    with KnowledgeGraphStore.connect(cfg) as handle:
        return reconcile(handle.raw, proj, cfg)


def _state_for(report, rel_tail: tuple[str, ...]) -> str:
    suffix = "/".join(rel_tail)
    matches = [d for d in report.documents if d.source_path.replace("\\", "/").endswith(suffix)]
    assert matches, f"no DocumentDriftRecord ending in {suffix!r}: {report.to_dict()}"
    return matches[0].state


# --- export baseline hash ----------------------------------------------------


def test_finalize_writes_exported_content_hash_matching_disk(tmp_path: Path) -> None:
    proj = _finalized_project(tmp_path)
    cfg = _config(proj)
    slot = EXPORTED_CONTENT_HASH_SLOT.split(":", 1)[1]
    with KnowledgeGraph.connect(cfg) as kg:
        ns = kg.config.ontology_namespace.rstrip("/") + "/"
        rows = list(
            kg.store.query(
                f"PREFIX cf: <{ns}> "
                "SELECT ?source_path ?h WHERE { "
                "  ?doc a cf:Document ; cf:source_path ?source_path ; "
                f"  cf:{slot} ?h }}"
            )
        )
    assert rows, "every Document must carry an exported_content_hash baseline"
    for row in rows:
        on_disk = proj / str(row["source_path"].value)
        expected = hashlib.sha256(on_disk.read_bytes()).hexdigest()
        assert str(row["h"].value) == expected


def test_baseline_updates_when_graph_changes_then_refinalized(tmp_path: Path) -> None:
    from cataforge.application.context import write as ctx_write

    proj = _finalized_project(tmp_path)
    first = _reconcile(proj)
    assert _state_for(first, PRD) == DRIFT_IN_SYNC
    first_baseline = _document_baseline(proj, PRD)

    _rewrite_a_section_body(proj, " [graph addendum]")
    ctx_write.finalize(str(proj))
    gc.collect()
    invalidate_cache()

    second_baseline = _document_baseline(proj, PRD)
    assert second_baseline != first_baseline
    # After re-export the disk, baseline and render all agree again.
    assert _state_for(_reconcile(proj), PRD) == DRIFT_IN_SYNC


# --- triage states -----------------------------------------------------------


def test_all_documents_in_sync_after_finalize(tmp_path: Path) -> None:
    report = _reconcile(_finalized_project(tmp_path))
    assert report.documents, "fixture must yield Document drift records"
    for d in report.documents:
        assert d.state == DRIFT_IN_SYNC, (d.source_path, d.state)
    assert report.document_drift_count == 0


def test_human_edit_to_exported_file(tmp_path: Path) -> None:
    proj = _finalized_project(tmp_path)
    prd = proj.joinpath(*PRD)
    prd.write_text(prd.read_text(encoding="utf-8") + "\n<!-- human note -->\n", encoding="utf-8")

    report = _reconcile(proj)
    assert _state_for(report, PRD) == DRIFT_HUMAN_EDIT


def test_graph_ahead_when_file_deleted(tmp_path: Path) -> None:
    proj = _finalized_project(tmp_path)
    proj.joinpath(*PRD).unlink()

    assert _state_for(_reconcile(proj), PRD) == DRIFT_GRAPH_AHEAD


def test_graph_ahead_when_graph_section_updated(tmp_path: Path) -> None:
    proj = _finalized_project(tmp_path)
    _rewrite_a_section_body(proj, " [graph-only edit]")

    assert _state_for(_reconcile(proj), PRD) == DRIFT_GRAPH_AHEAD


def test_conflict_when_both_sides_diverge(tmp_path: Path) -> None:
    proj = _finalized_project(tmp_path)
    # Graph side: mutate a section body so the render no longer matches baseline.
    _rewrite_a_section_body(proj, " [graph edit]")
    # File side: a human edit that differs from both baseline and render.
    prd = proj.joinpath(*PRD)
    prd.write_text(prd.read_text(encoding="utf-8") + "\n<!-- human note -->\n", encoding="utf-8")

    assert _state_for(_reconcile(proj), PRD) == DRIFT_CONFLICT


def test_never_exported_on_ingest_only_project(tmp_path: Path) -> None:
    report = _reconcile(_ingest_only_project(tmp_path))
    assert report.documents
    for d in report.documents:
        assert d.state == DRIFT_NEVER_EXPORTED, (d.source_path, d.state)
    assert report.document_drift_count == len(report.documents)


# --- id-diff regression ------------------------------------------------------


def test_triage_does_not_perturb_id_diff_counts(tmp_path: Path) -> None:
    """Content drift leaves the id-set diff untouched but gates ok in graph mode."""
    proj = _finalized_project(tmp_path)
    clean = _reconcile(proj)
    assert clean.overall_divergence_count == 0
    assert clean.ok is True

    # A human edit to the file's prose changes content triage but adds no new
    # entity/relation/section id, so the id-set diff stays clean. Under graph
    # mode ok follows the document triage, so the human edit flips ok to False
    # (it needs an ingest to absorb the out-of-band change).
    prd = proj.joinpath(*PRD)
    prd.write_text(prd.read_text(encoding="utf-8") + "\n<!-- comment -->\n", encoding="utf-8")
    drifted = _reconcile(proj)
    assert drifted.document_drift_count >= 1
    assert drifted.overall_divergence_count == 0
    assert drifted.ok is False


def test_to_dict_carries_triage_fields(tmp_path: Path) -> None:
    payload = _reconcile(_finalized_project(tmp_path)).to_dict()
    assert payload["mode"] == "graph"
    assert payload["document_drift_count"] == 0
    assert isinstance(payload["documents"], list) and payload["documents"]
    for record in payload["documents"]:
        assert set(record) == {
            "source_path",
            "doc_id",
            "state",
            "remediation",
            "desynced_sections",
        }
        # An in-sync document needs no remediation and carries no tile-cover
        # violation, whatever the authority.
        assert record["remediation"] == "none"
        assert record["desynced_sections"] == []


def test_reconcile_ok_gate_is_mode_aware() -> None:
    """The ok gate picks its authoritative signal by mode (R-003).

    graph: ok follows the document triage, so a per-doc_type symmetric-diff
    divergence (the lossy export→rescan false positive) is diagnostics only.
    markdown: there is no graph, so the symmetric diff is the only signal and
    gates ok directly.
    """
    per = {"prd": PerDocTypeReport(doc_type="prd", missing_entities=["F-001"])}
    in_sync = [
        DocumentDriftRecord(source_path="docs/prd/prd.md", doc_id="prd", state=DRIFT_IN_SYNC)
    ]

    graph = ReconcileReport(
        timestamp="t",
        active_doc_types=["prd"],
        per_doc_type=per,
        mode="graph",
        documents=in_sync,
    )
    assert graph.overall_divergence_count == 1  # symmetric diff flags a divergence
    assert graph.document_drift_count == 0
    assert graph.ok is True  # ... but graph gates on triage, so it is demoted

    markdown = ReconcileReport(
        timestamp="t",
        active_doc_types=["prd"],
        per_doc_type=per,
        mode="markdown",
        documents=in_sync,
    )
    assert markdown.ok is False  # markdown gates on the exact symmetric diff


# --- docs index rebuild on finalize ------------------------------------------


def test_finalize_rebuilds_doc_index(tmp_path: Path) -> None:
    import json

    from cataforge.application.context import write as ctx_write

    proj = _ingest_only_project(tmp_path)
    index_path = proj / "docs" / ".doc-index.json"
    # Seed a stale sentinel index; finalize must overwrite it with a fresh build.
    index_path.write_text(json.dumps({"documents": {"STALE": {}}}), encoding="utf-8")

    ctx_write.finalize(str(proj))
    gc.collect()

    assert index_path.is_file()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert "documents" in index
    assert "STALE" not in index["documents"], "index must be rebuilt, not left stale"


# --- helpers -----------------------------------------------------------------


def _document_baseline(proj: Path, rel_tail: tuple[str, ...]) -> str | None:
    cfg = _config(proj)
    suffix = "/".join(rel_tail)
    slot = EXPORTED_CONTENT_HASH_SLOT.split(":", 1)[1]
    with KnowledgeGraph.connect(cfg) as kg:
        ns = kg.config.ontology_namespace.rstrip("/") + "/"
        for row in kg.store.query(
            f"PREFIX cf: <{ns}> "
            "SELECT ?source_path ?h WHERE { "
            f"  ?doc a cf:Document ; cf:source_path ?source_path ; cf:{slot} ?h }}"
        ):
            if str(row["source_path"].value).replace("\\", "/").endswith(suffix):
                return str(row["h"].value)
    return None


def _rewrite_a_section_body(proj: Path, suffix_text: str) -> None:
    """Append text to one level-2 section body of the PRD in the graph only.

    Leaves the on-disk file untouched so the fresh render diverges from both
    the file bytes and the export baseline. The section is re-staged under the
    same ``source_doc`` (``prd``) so its IRI — and the rebuilt document — match.
    """
    cfg = _config(proj)
    doc_id = "prd"
    with KnowledgeGraph.connect(cfg) as kg:
        ns = kg.config.ontology_namespace.rstrip("/") + "/"
        rows = list(
            kg.store.query(
                f"PREFIX cf: <{ns}> "
                "SELECT ?anchor ?body WHERE { "
                "  ?s a cf:Section ; cf:source_doc ?src ; "
                "     cf:section_anchor ?anchor ; cf:narrative_body ?body ; "
                '     cf:section_level "2" . '
                f'  FILTER(?src = "{doc_id}") '
                "} ORDER BY ?anchor LIMIT 1"
            )
        )
        assert rows, "no level-2 section to mutate"
        anchor = str(rows[0]["anchor"].value)
        new_body = str(rows[0]["body"].value) + suffix_text
        with kg.transaction() as txn:
            txn.add_section(doc_id, anchor, new_body, hashlib.sha256(new_body.encode()).hexdigest())
    gc.collect()
    invalidate_cache()
