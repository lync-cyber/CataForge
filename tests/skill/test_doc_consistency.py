"""Tests for cross-document consistency validation (doc-consistency skill)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from cataforge.core.types import Severity
from cataforge.runtime.skill.builtins.doc_consistency.checker import CrossDocChecker


@pytest.fixture()
def docs_dir(tmp_path: Path) -> Path:
    """Create a minimal docs directory structure."""
    for subdir in ("prd", "arch", "ui-spec", "dev-plan"):
        (tmp_path / subdir).mkdir()
    return tmp_path


def _write(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


# ---- PRD → ARCH AC traceability ----


def test_prd_arch_ac_coverage_missing(docs_dir: Path) -> None:
    _write(
        docs_dir / "prd" / "prd-test.md",
        """\
        ---
        id: prd-test
        author: pm
        status: approved
        deps: []
        consumers: [architect]
        ---
        ## 2. Features
        ### F-001: Login
        AC-001: User can login with email
        AC-002: User can login with phone
        AC-003: Rate limit after 5 failures
        """,
    )
    _write(
        docs_dir / "arch" / "arch-test.md",
        """\
        ---
        id: arch-test
        author: architect
        status: approved
        deps: [prd-test]
        consumers: [tech-lead]
        ---
        ## 2. Modules
        ### M-001: Auth
        Maps F-001, AC-001
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    checker.check_prd_arch_ac_coverage()
    assert len(checker.errors) == 1
    assert "AC-002" in checker.errors[0].message or "AC-003" in checker.errors[0].message


def test_prd_arch_ac_coverage_full(docs_dir: Path) -> None:
    _write(
        docs_dir / "prd" / "prd-test.md",
        """\
        ---
        id: prd-test
        author: pm
        status: approved
        deps: []
        consumers: [architect]
        ---
        ## 2. Features
        ### F-001: Login
        AC-001: User can login
        """,
    )
    _write(
        docs_dir / "arch" / "arch-test.md",
        """\
        ---
        id: arch-test
        author: architect
        status: approved
        deps: [prd-test]
        consumers: [tech-lead]
        ---
        ## 2. Modules
        ### M-001: Auth
        Maps F-001, AC-001
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    checker.check_prd_arch_ac_coverage()
    assert len(checker.errors) == 0


# ---- PRD → ARCH priority alignment ----


def test_prd_arch_p0_missing_in_arch(docs_dir: Path) -> None:
    _write(
        docs_dir / "prd" / "prd-test.md",
        """\
        ---
        id: prd-test
        author: pm
        status: approved
        deps: []
        consumers: [architect]
        ---
        ## 2. Features
        ### F-001: Critical Login
        - 优先级: P0
        ### F-002: Nice-to-have Export
        - 优先级: P2
        """,
    )
    _write(
        docs_dir / "arch" / "arch-test.md",
        """\
        ---
        id: arch-test
        author: architect
        status: approved
        deps: [prd-test]
        consumers: [tech-lead]
        ---
        ## 2. Modules
        ### M-001: Export
        Maps F-002
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    checker.check_prd_arch_priority_alignment()
    assert len(checker.errors) == 1
    assert "F-001" in checker.errors[0].message
    assert checker.errors[0].severity == Severity.CRITICAL


# ---- ARCH → DEV-PLAN API contract ----


def test_arch_devplan_api_contract_mismatch(docs_dir: Path) -> None:
    _write(
        docs_dir / "arch" / "arch-test.md",
        """\
        ---
        id: arch-test
        author: architect
        status: approved
        deps: [prd-test]
        consumers: [tech-lead]
        ---
        ## 3. API
        ### API-001: Login
        POST /auth/login
        request: {email, password}
        """,
    )
    _write(
        docs_dir / "dev-plan" / "dev-plan-test.md",
        """\
        ---
        id: dev-plan-test
        author: tech-lead
        status: approved
        deps: [arch-test]
        consumers: [implementer]
        ---
        ## 3. Tasks
        ### T-001: Implement login
        AC-001: Given valid creds, When POST /login, Then 200
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    checker.check_arch_devplan_api_contract()
    assert len(checker.errors) == 1
    assert "API-001" in checker.errors[0].message
    assert "/auth/login" in checker.errors[0].message


def test_arch_devplan_api_contract_match(docs_dir: Path) -> None:
    _write(
        docs_dir / "arch" / "arch-test.md",
        """\
        ---
        id: arch-test
        author: architect
        status: approved
        deps: [prd-test]
        consumers: [tech-lead]
        ---
        ## 3. API
        ### API-001: Login
        POST /auth/login
        """,
    )
    _write(
        docs_dir / "dev-plan" / "dev-plan-test.md",
        """\
        ---
        id: dev-plan-test
        author: tech-lead
        status: approved
        deps: [arch-test]
        consumers: [implementer]
        ---
        ## 3. Tasks
        ### T-001: Implement login
        AC-001: When POST /auth/login, Then 200
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    checker.check_arch_devplan_api_contract()
    assert len(checker.errors) == 0


# ---- PRD → DEV-PLAN AC traceability ----


def test_prd_devplan_ac_missing(docs_dir: Path) -> None:
    _write(
        docs_dir / "prd" / "prd-test.md",
        """\
        ---
        id: prd-test
        author: pm
        status: approved
        deps: []
        consumers: [architect]
        ---
        ## 2. Features
        ### F-001: Login
        AC-001: email login
        AC-002: phone login
        AC-003: rate limit
        """,
    )
    _write(
        docs_dir / "dev-plan" / "dev-plan-test.md",
        """\
        ---
        id: dev-plan-test
        author: tech-lead
        status: approved
        deps: [arch-test]
        consumers: [implementer]
        ---
        ## 3. Tasks
        ### T-001: Login
        tdd_acceptance:
        - AC-001: email login works
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    checker.check_prd_devplan_ac_traceability()
    assert len(checker.errors) == 1
    assert "2" in checker.errors[0].message  # 2 missing ACs


# ---- Orphaned components ----


def test_orphaned_ui_components(docs_dir: Path) -> None:
    _write(
        docs_dir / "ui-spec" / "ui-spec-test.md",
        """\
        ---
        id: ui-spec-test
        author: ui-designer
        status: approved
        deps: [prd-test]
        consumers: [tech-lead]
        ---
        ## 2. Components
        ### C-001: LoginForm
        Props: email, password
        ### C-002: OrphanWidget
        Props: data
        ## 3. Pages
        ### P-001: LoginPage
        Uses C-001
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    checker.check_orphaned_components()
    assert len(checker.warnings) == 1
    assert "C-002" in checker.warnings[0].message


# ---- Traceability matrix ----


def test_traceability_matrix_coverage(docs_dir: Path) -> None:
    _write(
        docs_dir / "prd" / "prd-test.md",
        """\
        ---
        id: prd-test
        author: pm
        status: approved
        deps: []
        consumers: [architect]
        ---
        ## 2. Features
        ### F-001: Login
        AC-001: can login
        ### F-002: Export
        AC-002: can export
        """,
    )
    _write(
        docs_dir / "arch" / "arch-test.md",
        """\
        ---
        id: arch-test
        author: architect
        status: approved
        deps: [prd-test]
        consumers: [tech-lead]
        ---
        ## 2. Modules
        ### M-001: Auth
        Maps F-001
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    matrix = checker.build_traceability_matrix()
    assert len(matrix) == 2
    f001 = next(r for r in matrix if r["feature"] == "F-001")
    f002 = next(r for r in matrix if r["feature"] == "F-002")
    assert f001["coverage"] == "partial"
    assert f002["coverage"] == "missing"


# ---- Run orchestration ----


def test_run_returns_0_when_consistent(docs_dir: Path) -> None:
    _write(
        docs_dir / "prd" / "prd-test.md",
        """\
        ---
        id: prd-test
        author: pm
        status: approved
        deps: []
        consumers: [architect]
        ---
        ## 2. Features
        ### F-001: Login
        AC-001: can login
        """,
    )
    _write(
        docs_dir / "arch" / "arch-test.md",
        """\
        ---
        id: arch-test
        author: architect
        status: approved
        deps: [prd-test]
        consumers: [tech-lead]
        ---
        ## 2. Modules
        ### M-001: Auth
        Maps F-001, AC-001
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    result = checker.run()
    assert result == 0


def test_run_returns_1_on_critical(docs_dir: Path) -> None:
    _write(
        docs_dir / "prd" / "prd-test.md",
        """\
        ---
        id: prd-test
        author: pm
        status: approved
        deps: []
        consumers: [architect]
        ---
        ## 2. Features
        ### F-001: Critical Feature
        - 优先级: P0
        AC-001: must work
        """,
    )
    _write(
        docs_dir / "arch" / "arch-test.md",
        """\
        ---
        id: arch-test
        author: architect
        status: approved
        deps: [prd-test]
        consumers: [tech-lead]
        ---
        ## 2. Modules
        ### M-001: Unrelated
        Maps F-999
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    result = checker.run()
    assert result == 1


def test_run_skips_with_single_doc(docs_dir: Path) -> None:
    _write(
        docs_dir / "prd" / "prd-test.md",
        """\
        ---
        id: prd-test
        author: pm
        status: approved
        deps: []
        consumers: [architect]
        ---
        ## 2. Features
        ### F-001: Login
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    result = checker.run()
    assert result == 0
