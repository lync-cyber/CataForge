"""``ingest`` must leave absorbed documents finalize-convergent (issue #472).

Ingest previously reflowed entities/sections into the graph but never touched
the ``cf:exported_content_hash`` baseline — only finalize wrote it. A project
that (safely) used ingest instead of finalize therefore stayed
``never_exported`` forever: finalize blocked, and the doc's KG-only enrichment
edges were misclassified as ghost drift.
"""

from __future__ import annotations

import gc
import json
import shutil
from pathlib import Path

import pytest

from cataforge.application.context import write as cw
from cataforge.domain.kg import KGConfig, init_store
from cataforge.domain.kg._dispatch import invalidate_cache
from cataforge.domain.kg.authority import DRIFT_IN_SYNC, DRIFT_NEVER_EXPORTED

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


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
    shutil.copytree(FIXTURE_ROOT / "waterfall" / "docs", proj / "docs")
    cfg = KGConfig(
        store_backend="oxigraph",
        db_path=proj / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test-report"},
    )
    handle = init_store(cfg, force=True)
    handle.raw.flush()
    handle.close()
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps(
            {"context": {"mode": "graph", "kg_active_doc_types": ["prd", "arch", "test-report"]}}
        ),
        encoding="utf-8",
    )
    invalidate_cache()
    gc.collect()
    return proj


def test_ingest_alone_reaches_in_sync(tmp_path: Path) -> None:
    """Ingest stamps the absorbed baseline, so reconcile converges without a
    finalize run — the ingest-as-workaround loop is no longer a dead end."""
    proj = _project(tmp_path)
    cw.ingest(str(proj))
    gc.collect()
    report = cw.reconcile_check(str(proj))
    gc.collect()
    states = {d.source_path: d.state for d in report.documents}
    assert states and all(s != DRIFT_NEVER_EXPORTED for s in states.values()), states
    assert all(s == DRIFT_IN_SYNC for s in states.values()), states
    assert report.ok, report.to_dict()


def test_ingest_then_finalize_not_blocked(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.ingest(str(proj))
    gc.collect()
    result = cw.finalize(str(proj), dry_run=True)
    gc.collect()
    blocked = [r for r in result.file_records if r.action == "blocked"]
    assert blocked == [], [r.output_path for r in blocked]


def test_lossy_absorb_is_not_stamped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When the graph render does not reproduce the file content, stamping the
    baseline would authorize finalize to overwrite the richer disk state (the
    #421 data-loss class) — such documents must stay never_exported."""
    import cataforge.domain.kg.export.document_pipeline as dp

    proj = _project(tmp_path)
    monkeypatch.setattr(dp, "content_equivalent", lambda a, b: False)
    cw.ingest(str(proj))
    gc.collect()
    monkeypatch.undo()
    report = cw.reconcile_check(str(proj))
    gc.collect()
    states = {d.source_path: d.state for d in report.documents}
    assert states and all(s == DRIFT_NEVER_EXPORTED for s in states.values()), states
