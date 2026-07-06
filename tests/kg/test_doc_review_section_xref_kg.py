"""check_xref KG path verifies a bare section ref against ``cf:Section`` nodes.

With KG active for the doc_type, ``arch#§2`` must resolve to a Section of the
``arch`` document (anchor ``§2 Modules`` in the vertical-slice fixture); a
number with no matching section fails instead of being silently skipped.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _setup_project(tmp_path: Path) -> Path:
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    project = tmp_path / "project"
    project.mkdir()
    (project / ".cataforge").mkdir()

    config = KGConfig(
        store_backend="oxigraph",
        db_path=project / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "test"},
    )
    handle = init_store(config, force=True)
    run_migration(handle.raw, FIXTURE_ROOT / "waterfall", config)
    handle.raw.flush()

    (project / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"kg_active_doc_types": ["prd", "arch", "test"]}}),
        encoding="utf-8",
    )
    (project / "docs").mkdir()
    return project


def _check(project: Path, body: str) -> list[str]:
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

    doc = project / "docs" / "prd.md"
    doc.write_text(
        "---\nid: prd\nauthor: pm\nstatus: draft\ndeps: []\nconsumers: []\n---\n"
        f"# PRD\n\n## 1. Overview\n\n{body}\n",
        encoding="utf-8",
    )
    invalidate_cache()
    checker = DocChecker("prd", str(doc), docs_dir=str(project / "docs"), quiet=True)
    checker.check_xref()
    return checker.errors


def test_kg_valid_bare_section_ref_passes(tmp_path: Path) -> None:
    errors = _check(_setup_project(tmp_path), "模块划分见 arch#§2")
    assert not any("arch#§2" in e for e in errors), errors


def test_kg_broken_bare_section_ref_fails(tmp_path: Path) -> None:
    errors = _check(_setup_project(tmp_path), "模块划分见 arch#§9")
    assert any("arch#§9" in e for e in errors), errors


def test_kg_doc_without_sections_not_flagged(tmp_path: Path) -> None:
    # A doc the graph holds no Section nodes for is outside this check's
    # jurisdiction — no false positive.
    errors = _check(_setup_project(tmp_path), "变更记录见 changelog#§1")
    assert not any("changelog#§1" in e for e in errors), errors
