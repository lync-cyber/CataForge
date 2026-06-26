"""Doctor `kg_snapshot_freshness` gate — graph mode only, WARN-not-FAIL.

The gitignored store rebuilds from the latest NQuads snapshot on clone, so a
snapshot lagging the live store risks losing uncommitted graph state. The gate
nudges `cataforge context finalize` without failing the doctor exit code.
"""

from __future__ import annotations

import gc
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from cataforge.application.context import write as cw
from cataforge.domain.kg._dispatch import invalidate_cache

_GRAPH_DOC = (
    "---\nid: prd\ndoc_type: prd\nauthor: product-manager\nstatus: draft\ndeps: []\n---\n"
    "# PRD\n\n引言。\n\n## §1 功能\n\n### F-001 登录\n\n用户可登录。\n\n"
)
_GRAPH_DOC2 = (
    "---\nid: arch\ndoc_type: arch\nauthor: architect\nstatus: draft\ndeps: []\n---\n"
    "# ARCH\n\n引言。\n\n## §1 接口\n\n### API-001 登录接口\n\n登录端点。\n\n"
)


@dataclass
class FakePaths:
    root: Path

    @property
    def framework_json(self) -> Path:
        return self.root / ".cataforge" / "framework.json"


@dataclass
class FakeConfig:
    paths: FakePaths


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    gc.collect()
    yield
    invalidate_cache()
    gc.collect()


def _project(tmp_path: Path, *, mode: str = "graph") -> Path:
    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    (proj / "docs").mkdir()
    ctx = {"mode": mode, "kg_active_doc_types": ["prd", "arch"]}
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": ctx}), encoding="utf-8"
    )
    invalidate_cache()
    gc.collect()
    return proj


def _check(proj: Path, capsys) -> tuple[int, str]:
    from cataforge.interface.cli.doctor.kg_ingestion import check_kg_snapshot_freshness

    rc = check_kg_snapshot_freshness(FakeConfig(paths=FakePaths(root=proj)))
    return rc, capsys.readouterr().out


def test_freshness_ok_after_finalize(tmp_path: Path, capsys) -> None:
    proj = _project(tmp_path)
    cw.ensure_store(str(proj))
    gc.collect()
    cw.author_document(str(proj), _GRAPH_DOC, source_path="docs/prd/prd.md")
    gc.collect()
    cw.finalize(str(proj))
    gc.collect()

    rc, out = _check(proj, capsys)
    assert rc == 0
    assert "OK" in out


def test_freshness_warns_when_store_ahead_of_snapshot(tmp_path: Path, capsys) -> None:
    proj = _project(tmp_path)
    cw.ensure_store(str(proj))
    gc.collect()
    cw.author_document(str(proj), _GRAPH_DOC, source_path="docs/prd/prd.md")
    gc.collect()
    cw.finalize(str(proj))
    gc.collect()
    cw.author_document(str(proj), _GRAPH_DOC2, source_path="docs/arch/arch.md")  # no finalize
    gc.collect()

    rc, out = _check(proj, capsys)
    assert rc == 0  # WARN-only, non-gating
    assert "WARN" in out
    assert "stale" in out


def test_freshness_warns_when_no_snapshot(tmp_path: Path, capsys) -> None:
    proj = _project(tmp_path)
    cw.ensure_store(str(proj))
    gc.collect()
    cw.author_document(str(proj), _GRAPH_DOC, source_path="docs/prd/prd.md")  # no finalize
    gc.collect()

    rc, out = _check(proj, capsys)
    assert rc == 0
    assert "WARN" in out
    assert "no NQuads snapshot" in out


def test_freshness_skips_non_graph_mode(tmp_path: Path, capsys) -> None:
    proj = _project(tmp_path, mode="markdown")
    rc, out = _check(proj, capsys)
    assert rc == 0
    assert "skipping" in out


def test_freshness_skips_when_store_absent(tmp_path: Path, capsys) -> None:
    proj = _project(tmp_path)  # graph mode but never hydrated
    rc, out = _check(proj, capsys)
    assert rc == 0
    assert "skipping" in out
