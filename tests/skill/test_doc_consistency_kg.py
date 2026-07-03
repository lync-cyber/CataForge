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
    """Smoke: AC coverage check runs through the KG dispatch chain without raising."""
    project = _project_with_kg(tmp_path, active=["prd", "arch", "test"])

    checker = CrossDocChecker(docs_dir=str(project / "docs"), quiet=True)
    # No exception means the dispatch chain (kg query → fallback) is wired
    checker.check_prd_arch_ac_coverage()
    checker.check_prd_devplan_ac_traceability()


def test_arch_ac_coverage_accepts_transitive_feature_impl(tmp_path: Path) -> None:
    """arch covers an AC transitively when its parent Feature is implemented by
    an arch module. arch asserts ``cf:implements`` on Features and never names
    AC-NNN directly, so a direct arch→AC edge requirement is structurally
    unsatisfiable at the architecture phase.
    """
    project = _project_with_kg(tmp_path, active=["prd", "arch", "test"])

    checker = CrossDocChecker(docs_dir=str(project / "docs"), quiet=True)
    checker.check_prd_arch_ac_coverage()

    ac_issues = [e for e in checker.errors if "未在 ARCH" in e.message]
    assert not ac_issues, f"all Features implemented → all ACs covered: {ac_issues}"


def test_arch_ac_coverage_flags_ac_of_unimplemented_feature(tmp_path: Path) -> None:
    """Regression: an AC whose parent Feature has no arch impl is still flagged —
    the transitive relaxation must not collapse into an always-covered no-op.
    """
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    project = tmp_path / "partial"
    project.mkdir()
    (project / ".cataforge").mkdir()
    docs = project / "docs"
    _write(
        docs / "prd" / "prd-p.md",
        """\
        ---
        doc_id: prd
        doc_type: prd
        ---
        # PRD
        ## §2 Features
        ### §2.1 F-001 登录
        允许用户登录。
        #### AC-001 可登录
        输入合法对返回 200。
        ### §2.2 F-002 登出
        允许用户登出。
        #### AC-002 可登出
        调用 logout 返回 204。
        """,
    )
    _write(
        docs / "arch" / "arch-p.md",
        """\
        ---
        doc_id: arch
        doc_type: arch
        ---
        # Architecture
        ## §2 Modules
        ### §2.1 M-001 认证模块
        - 映射功能: prd#§2.F-001
        暴露 POST /login。
        """,
    )

    config = KGConfig(
        store_backend="oxigraph",
        db_path=project / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch"},
    )
    handle = init_store(config, force=True)
    run_migration(handle.raw, project, config)
    handle.raw.flush()
    handle.close()
    (project / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"kg_active_doc_types": ["prd", "arch"]}}),
        encoding="utf-8",
    )

    checker = CrossDocChecker(docs_dir=str(docs), quiet=True)
    checker.check_prd_arch_ac_coverage()

    messages = " ".join(e.message for e in checker.errors)
    assert "AC-002" in messages, f"AC-002 (parent F-002 unimplemented) must be flagged: {messages}"
    assert "AC-001" not in messages, (
        f"AC-001 (parent F-001 implemented) must not be flagged: {messages}"
    )


def test_regex_arch_ac_coverage_accepts_parent_feature_mention(tmp_path: Path) -> None:
    """Non-KG arch: an AC is covered when its parent Feature appears in arch,
    even if the AC id itself is never written. Mirrors the KG transitive rule so
    both paths agree on the arch→Feature→AC coverage semantics.
    """
    project = tmp_path / "proj"
    docs = project / "docs"
    docs.mkdir(parents=True)
    (project / ".cataforge").mkdir()
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
        Implements F-001 fully.
        """,
    )

    checker = CrossDocChecker(docs_dir=str(docs), quiet=True)
    checker.check_prd_arch_ac_coverage()

    assert not any("AC-001" in e.message for e in checker.errors)


def test_devplan_local_numbering_reads_feature_level_coverage(tmp_path: Path) -> None:
    """Same bare AC id under two Features → per-feature coverage: only the
    feature no task references is flagged, not every colliding token."""
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    project = tmp_path / "local-num"
    project.mkdir()
    (project / ".cataforge").mkdir()
    docs = project / "docs"
    _write(
        docs / "prd" / "prd-p.md",
        """\
        ---
        doc_id: prd
        doc_type: prd
        ---
        # PRD
        ## §2 Features
        ### §2.1 F-001 登录
        允许用户登录。
        #### AC-001 可登录
        输入合法对返回 200。
        ### §2.2 F-002 登出
        允许用户登出。
        #### AC-001 可登出
        调用 logout 返回 204。
        """,
    )
    _write(
        docs / "dev-plan" / "dev-plan-p.md",
        """\
        ---
        doc_id: dev-plan
        doc_type: dev-plan
        ---
        # Dev Plan
        ## §3 Tasks
        ### §3.1 T-001 实现登录
        - 映射功能: prd#§2.F-001
        写登录端点。
        """,
    )

    config = KGConfig(
        store_backend="oxigraph",
        db_path=project / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "dev-plan"},
    )
    handle = init_store(config, force=True)
    run_migration(handle.raw, project, config)
    handle.raw.flush()
    handle.close()
    (project / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"kg_active_doc_types": ["prd", "dev-plan"]}}),
        encoding="utf-8",
    )

    checker = CrossDocChecker(docs_dir=str(docs), quiet=True)
    checker.check_prd_devplan_ac_traceability()

    messages = " ".join(e.message for e in checker.errors)
    assert "F-002" in messages, f"unreferenced F-002 must be flagged: {messages}"
    assert "F-001" not in messages, f"referenced F-001 must not be flagged: {messages}"
