"""KG dispatch tests for doc-consistency AC traceability checks.

Wave C (P1-2): ``check_prd_arch_ac_coverage`` and
``check_prd_devplan_ac_traceability`` switch from regex set-difference
to SPARQL when the project's doc_types are KG-active. Fallback path is
exercised to verify regex still works when KG is unavailable.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from cataforge.runtime.skill.builtins.doc_consistency.checker import CrossDocChecker


@pytest.fixture(autouse=True)
def reset_dispatch_cache():
    from cataforge.domain.kg._dispatch import invalidate_cache

    invalidate_cache()
    yield
    invalidate_cache()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


# ---------------------------------------------------------------------------
# KG-inactive: regex path still works (regression guard)
# ---------------------------------------------------------------------------


def test_regex_path_runs_when_no_kg_store(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    docs = project / "docs"
    docs.mkdir(parents=True)
    (project / ".cataforge").mkdir()
    # No store dir → _active_doc_types() returns empty → regex path
    (project / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"kg_active_doc_types": ["prd", "arch"]}}),
        encoding="utf-8",
    )

    _write(
        docs / "prd" / "prd-x.md",
        """\
        ---
        id: prd-x
        ---
        ## 2. Features
        ### F-001: Foo
        AC-001 must work
        AC-002 must also work
        """,
    )
    _write(
        docs / "arch" / "arch-x.md",
        """\
        ---
        id: arch-x
        ---
        ## 2. Modules
        ### M-001
        Implements AC-001 only
        """,
    )

    checker = CrossDocChecker(docs_dir=str(docs), quiet=True)
    checker.check_prd_arch_ac_coverage()

    # Regex set-difference: AC-002 is missing in ARCH
    assert any("AC-002" in e.message for e in checker.errors)


# ---------------------------------------------------------------------------
# KG-inactive (empty active set): no KG dispatch attempted
# ---------------------------------------------------------------------------


def test_active_doc_types_empty_when_no_framework_json(tmp_path: Path) -> None:
    """No project root → _active_doc_types() is empty set."""
    docs = tmp_path / "loose-docs"
    docs.mkdir()
    (docs / "prd").mkdir()
    (docs / "arch").mkdir()

    checker = CrossDocChecker(docs_dir=str(docs), quiet=True)
    # No .cataforge sibling → project_root resolution fails
    assert checker._active_doc_types() == set()


# ---------------------------------------------------------------------------
# KG-active: dispatch path exercised end-to-end on ingested fixture
# ---------------------------------------------------------------------------

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _project_with_kg(tmp_path: Path, *, active: list[str]) -> Path:
    """Build a project with ingested KG (fixture) + framework.json."""
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    project = tmp_path / "project"
    project.mkdir()
    (project / ".cataforge").mkdir()

    config = KGConfig(
        store_backend="oxigraph",
        db_path=project / ".cataforge" / "kg" / "store",
        kg_active_doc_types=set(active),
    )
    handle = init_store(config, force=True)
    run_migration(handle.raw, FIXTURE_ROOT / "waterfall", config)
    handle.raw.flush()
    handle.close()

    (project / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"kg_active_doc_types": active}}), encoding="utf-8"
    )

    # Mirror the fixture docs into the project so CrossDocChecker can read them
    fixture_docs = FIXTURE_ROOT / "waterfall" / "docs"
    for doc_type_dir in fixture_docs.iterdir():
        if not doc_type_dir.is_dir():
            continue
        target = project / "docs" / doc_type_dir.name
        target.mkdir(parents=True, exist_ok=True)
        for md in doc_type_dir.glob("*.md"):
            (target / md.name).write_bytes(md.read_bytes())
    return project


def test_kg_dispatch_resolves_active_doc_types(tmp_path: Path) -> None:
    project = _project_with_kg(tmp_path, active=["prd", "arch", "test"])

    checker = CrossDocChecker(docs_dir=str(project / "docs"), quiet=True)
    active = checker._active_doc_types()

    assert "prd" in active
    assert "arch" in active


def test_kg_dispatch_runs_check_without_error(tmp_path: Path) -> None:
    """Smoke: AC coverage check runs through the KG dispatch chain without raising.

    The fixture vertical slice has no ingested AC entities (only F/M/T), so
    the KG helper returns ``None`` (no PRD ACs in store) and the regex
    fallback takes over. Asserts the chain completes; downstream-found
    issues from regex are validated by the regex-path tests, not here.
    """
    project = _project_with_kg(tmp_path, active=["prd", "arch", "test"])

    checker = CrossDocChecker(docs_dir=str(project / "docs"), quiet=True)
    # No exception means the dispatch chain (kg query → fallback) is wired
    checker.check_prd_arch_ac_coverage()
    checker.check_prd_devplan_ac_traceability()
