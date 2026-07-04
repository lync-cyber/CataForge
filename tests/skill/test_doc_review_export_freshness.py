"""doc-review export-freshness gate: reviewing a stale graph export must fail
fast instead of burning a review cycle on superseded text."""

from __future__ import annotations

import gc
import json
from pathlib import Path

import pytest

from cataforge.domain.kg._dispatch import invalidate_cache
from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker
from tests.kg.test_reconcile_triage import _finalized_project
from tests.kg.test_section_sync import (
    AC_LOGIN_BLOCK,
    ANCHOR_L3_LOGIN,
    _finalize,
    _prd_path,
    _write,
)

pytestmark = pytest.mark.usefixtures("_isolate_cache")


@pytest.fixture
def _isolate_cache():
    invalidate_cache()
    yield
    invalidate_cache()


REVISION = f"### {ANCHOR_L3_LOGIN}\n\n[REV] 修订后的登录能力描述。\n\n{AC_LOGIN_BLOCK}"


def _freshness_errors(proj: Path) -> list[str]:
    checker = DocChecker("prd", str(_prd_path(proj)), docs_dir=str(proj / "docs"), quiet=True)
    checker.check_export_freshness()
    gc.collect()
    invalidate_cache()
    return checker.errors


def test_graph_ahead_export_blocks_review(tmp_path: Path) -> None:
    proj = _finalized_project(tmp_path)
    _write(proj, ANCHOR_L3_LOGIN, REVISION)  # authored, not yet finalized
    errors = _freshness_errors(proj)
    assert errors and any("finalize" in e for e in errors)


def test_fresh_export_passes(tmp_path: Path) -> None:
    proj = _finalized_project(tmp_path)
    _write(proj, ANCHOR_L3_LOGIN, REVISION)
    _finalize(proj)
    assert _freshness_errors(proj) == []


def test_markdown_mode_skips_silently(tmp_path: Path) -> None:
    proj = _finalized_project(tmp_path)
    fw = proj / ".cataforge" / "framework.json"
    data = json.loads(fw.read_text(encoding="utf-8"))
    data["context"]["mode"] = "markdown"
    fw.write_text(json.dumps(data), encoding="utf-8")
    invalidate_cache()
    assert _freshness_errors(proj) == []
