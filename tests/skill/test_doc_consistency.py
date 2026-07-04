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


# ---- docs_dir normalization: a volume subdir must not silently under-scan ----


def test_volume_subdir_docs_dir_normalizes_to_docs_root(tmp_path: Path) -> None:
    """Handed a volume subdir (docs/arch/), cross-doc discovery must resolve
    the project-global docs tree — not silently under-scan and false-clean."""
    (tmp_path / ".cataforge").mkdir()
    docs = tmp_path / "docs"
    (docs / "prd").mkdir(parents=True)
    (docs / "arch").mkdir(parents=True)
    _write(
        docs / "prd" / "prd-test.md",
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
        ### F-002: Reporting
        AC-002: Export CSV
        AC-003: Schedule report
        """,
    )
    _write(
        docs / "arch" / "arch-test.md",
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
    checker = CrossDocChecker(str(docs / "arch"), quiet=True)
    checker.check_prd_arch_ac_coverage()
    assert any("AC-002" in e.message for e in checker.errors), [e.message for e in checker.errors]


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
        ### F-002: Reporting
        AC-002: Export report as CSV
        AC-003: Schedule recurring report
        """,
    )
    # ARCH references F-001 (covering AC-001 transitively) but never F-002,
    # so F-002's ACs are genuinely uncovered.
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
    checker.check_prd_arch_ac_coverage()
    assert len(checker.errors) == 1
    message = checker.errors[0].message
    assert "AC-002" in message and "AC-003" in message
    assert "AC-001" not in message


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
        ### UC-001: LoginForm
        Props: email, password
        ### UC-002: OrphanWidget
        Props: data
        ## 3. Pages
        ### P-001: LoginPage
        Uses UC-001
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    checker.check_orphaned_components()
    assert len(checker.warnings) == 1
    assert "UC-002" in checker.warnings[0].message


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


# ---- AC traceability under per-feature local numbering ----


_PRD_LOCAL_NUMBERING = """\
---
id: prd-test
author: pm
status: approved
deps: []
consumers: [architect]
---
## 2. Features
### F-001: Login
- AC-001: User can login
- AC-002: Session persists
### F-002: Reporting
- AC-001: Export report as CSV
- AC-002: Schedule recurring report
- AC-003: Email digest
"""


def test_ac_traceability_local_numbering_covered_by_feature_refs(docs_dir: Path) -> None:
    """Per-feature AC sequences collide as bare tokens; coverage reads at
    feature level instead of flagging every same-numbered AC."""
    _write(docs_dir / "prd" / "prd-test.md", _PRD_LOCAL_NUMBERING)
    _write(
        docs_dir / "dev-plan" / "dev-plan-test.md",
        """\
        ---
        id: dev-plan-test
        author: tech-lead
        status: approved
        deps: [prd-test]
        consumers: [implementer]
        ---
        ## 3. Tasks
        ### T-001: Build login
        Maps F-001; tdd_acceptance: AC-001, AC-002
        ### T-002: Build reporting
        Maps F-002; tdd_acceptance: AC-001
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    checker.check_prd_devplan_ac_traceability()
    assert checker.errors == [], [e.message for e in checker.errors]


def test_ac_traceability_local_numbering_flags_unreferenced_feature(docs_dir: Path) -> None:
    _write(docs_dir / "prd" / "prd-test.md", _PRD_LOCAL_NUMBERING)
    _write(
        docs_dir / "dev-plan" / "dev-plan-test.md",
        """\
        ---
        id: dev-plan-test
        author: tech-lead
        status: approved
        deps: [prd-test]
        consumers: [implementer]
        ---
        ## 3. Tasks
        ### T-001: Build login
        Maps F-001; tdd_acceptance: AC-001, AC-002
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    checker.check_prd_devplan_ac_traceability()
    assert len(checker.errors) == 1
    assert "F-002" in checker.errors[0].message
    assert "F-001" not in checker.errors[0].message


# ---- Orphaned components: credit references outside page sections ----


def test_component_referenced_from_other_component_section(docs_dir: Path) -> None:
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
        ## 2. 组件清单
        | id | 名称 |
        |----|------|
        | UC-016 | StatusBar |
        ## 3. Components
        ### UC-001: Toolbar
        点击「+」插入按钮，触发 UC-015 抽屉。
        ### UC-015: InsertDrawer
        Props: items
        ### UC-016: StatusBar
        Props: state
        ### UC-017: NeverUsed
        Props: none
        ## 4. Pages
        ### P-001: EditorPage
        Uses UC-001
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    checker.check_orphaned_components()
    messages = " ".join(w.message for w in checker.warnings)
    assert "UC-015" not in messages, messages
    assert "UC-016" not in messages, messages
    assert "UC-017" in messages, messages


# ---- UI coverage: delivery-surface annotation ----


def test_ui_coverage_delivery_annotation(docs_dir: Path) -> None:
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
        ### F-010: 插件系统
        - delivery: dev-tooling
        - 开发者可注册渲染扩展，页面输出经插件管线处理。
        ### F-011: 设置页
        - delivery: ui
        - 提供偏好配置。
        """,
    )
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
        ## 3. Pages
        ### P-001: HomePage
        Nothing about those features.
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    checker.check_prd_uispec_user_facing_coverage()
    messages = " ".join(w.message for w in checker.warnings)
    assert "F-010" not in messages, messages
    assert "F-011" in messages, messages


# ---- Entity propagation: indirect credit via owning module ----


def test_entity_propagation_credited_via_module_reference(docs_dir: Path) -> None:
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
        ### M-001: Storage
        管理 E-001 文档实体的持久化。
        ### M-002: Sync
        管理 E-002 同步游标。
        ## 4. Entities
        ### E-001: Document
        ### E-002: SyncCursor
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
        ### T-001: Build storage
        实现 M-001 的读写路径。
        """,
    )
    checker = CrossDocChecker(str(docs_dir), quiet=True)
    checker.check_arch_devplan_entity_propagation()
    messages = " ".join(w.message for w in checker.warnings)
    assert "E-001" not in messages, messages
    assert "E-002" in messages, messages
