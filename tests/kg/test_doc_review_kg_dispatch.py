"""Integration tests for doc-review check_xref / check_bidirectional_coverage
KG dispatch (P2 task S3).

Verifies that the doc-review checker uses the KG path when the doc_type
is active and a store exists, and falls back to legacy file-glob when
the KG is inactive.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _setup_project(tmp_path: Path, variant: str = "waterfall", mode: str | None = None) -> Path:
    """Create a minimal CataForge project with an ingested KG store.

    `mode` writes ``context.mode`` (e.g. ``markdown``) so tests can assert the
    KG gates bypass even when a store exists on disk.
    """
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
    run_migration(handle.raw, FIXTURE_ROOT / variant, config)
    handle.raw.flush()

    context: dict = {"kg_active_doc_types": ["prd", "arch", "test"]}
    if mode is not None:
        context["mode"] = mode
    (project / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": context}), encoding="utf-8"
    )

    docs = project / "docs"
    docs.mkdir()
    return project


def _write_doc(project: Path, doc_type: str, content: str) -> Path:
    doc_file = project / "docs" / f"{doc_type}.md"
    doc_file.write_text(content, encoding="utf-8")
    return doc_file


_PRD_WITH_XREF = """\
---
id: prd-001
author: test
status: draft
deps: []
consumers: [arch]
---
[NAV]§1 §2[/NAV]

## 1. Overview

## 2. Features

### F-001 User login

Cross-ref: arch#§2.M-001
"""

_ARCH_CONTENT = """\
---
id: arch-001
author: test
status: draft
deps: [prd]
consumers: [dev-plan]
---
[NAV]§1 §2[/NAV]

## 1. Overview

## 2. Modules

### M-001 Auth module

Implements F-001.

### M-002 Data module

Implements F-002.
"""


def test_check_xref_uses_kg_when_active(tmp_path: Path) -> None:
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

    project = _setup_project(tmp_path)
    doc_file = _write_doc(project, "prd", _PRD_WITH_XREF)
    invalidate_cache()

    checker = DocChecker("prd", str(doc_file), docs_dir=str(project / "docs"), quiet=True)
    checker.check_xref()

    xref_failures = [e for e in checker.errors if "交叉引用" in e]
    assert not xref_failures, f"KG-active xref check should resolve M-001: {xref_failures}"


def test_check_xref_reports_missing_entity_via_kg(tmp_path: Path) -> None:
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

    project = _setup_project(tmp_path)
    content = _PRD_WITH_XREF.replace("arch#§2.M-001", "arch#§2.M-999")
    doc_file = _write_doc(project, "prd", content)
    invalidate_cache()

    checker = DocChecker("prd", str(doc_file), docs_dir=str(project / "docs"), quiet=True)
    checker.check_xref()

    xref_failures = [e for e in checker.errors if "KG" in e]
    assert xref_failures, "should report M-999 as missing in KG"


def test_check_xref_falls_back_when_kg_inactive(tmp_path: Path) -> None:
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

    project = tmp_path / "no-kg"
    project.mkdir()
    (project / ".cataforge").mkdir()
    docs = project / "docs"
    docs.mkdir()

    doc_file = _write_doc(project, "prd", _PRD_WITH_XREF)
    invalidate_cache()

    checker = DocChecker("prd", str(doc_file), docs_dir=str(docs), quiet=True)
    checker.check_xref()
    assert checker._maybe_kg_xref_resolvers() is None


def test_bidirectional_coverage_uses_kg_when_active(tmp_path: Path) -> None:
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

    project = _setup_project(tmp_path)
    doc_file = _write_doc(project, "arch", _ARCH_CONTENT)
    invalidate_cache()

    checker = DocChecker("arch", str(doc_file), docs_dir=str(project / "docs"), quiet=True)
    ran_kg = checker._kg_bidirectional_coverage("F")
    assert ran_kg, "should have used KG path for bidirectional coverage"


def test_coverage_row_uncovered_predicate() -> None:
    """The per-row coverage predicate: an implementing artifact alone covers a
    Feature unless the gate explicitly demands a verifying TestCase."""
    from cataforge.runtime.skill.builtins.doc_review.checker import (
        _coverage_row_uncovered,
    )

    # impl present, no test, gate does not require test → covered
    assert _coverage_row_uncovered(has_impl=True, has_test=False, require_test=False) is False
    # impl present, no test, gate requires test → uncovered
    assert _coverage_row_uncovered(has_impl=True, has_test=False, require_test=True) is True
    # no impl → uncovered regardless of require_test
    assert _coverage_row_uncovered(has_impl=False, has_test=True, require_test=False) is True
    assert _coverage_row_uncovered(has_impl=False, has_test=False, require_test=True) is True
    # impl + test, gate requires test → covered
    assert _coverage_row_uncovered(has_impl=True, has_test=True, require_test=True) is False


def test_bidirectional_coverage_passes_arch_without_testcases(tmp_path: Path) -> None:
    """arch with every upstream Feature implemented but zero TestCase reaching a
    Feature must PASS L1. TestCases are a later-phase artifact, so a coverage
    gate that demands has_test is structurally unsatisfiable at the arch phase.
    """
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

    project = _setup_project(tmp_path)
    doc_file = _write_doc(project, "arch", _ARCH_CONTENT)
    invalidate_cache()

    checker = DocChecker("arch", str(doc_file), docs_dir=str(project / "docs"), quiet=True)
    ran_kg = checker._kg_bidirectional_coverage("F")
    assert ran_kg
    assert not checker.errors, f"arch coverage must not demand TestCases: {checker.errors}"


def test_bidirectional_coverage_falls_back_when_inactive(
    tmp_path: Path,
) -> None:
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

    project = tmp_path / "no-kg"
    project.mkdir()
    (project / ".cataforge").mkdir()
    docs = project / "docs"
    docs.mkdir()

    doc_file = _write_doc(project, "arch", _ARCH_CONTENT)
    invalidate_cache()

    checker = DocChecker("arch", str(doc_file), docs_dir=str(docs), quiet=True)
    ran_kg = checker._kg_bidirectional_coverage("F")
    assert not ran_kg, "should fall back to legacy when KG not active"


def test_xref_bypasses_kg_under_doc_only_despite_store(tmp_path: Path) -> None:
    """markdown mode must ignore an on-disk store and use the file path."""
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

    project = _setup_project(tmp_path, mode="markdown")
    doc_file = _write_doc(project, "prd", _PRD_WITH_XREF)
    invalidate_cache()

    checker = DocChecker("prd", str(doc_file), docs_dir=str(project / "docs"), quiet=True)
    assert checker._maybe_kg_xref_resolvers() is None


def test_bidirectional_coverage_bypasses_kg_under_doc_only_despite_store(
    tmp_path: Path,
) -> None:
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

    project = _setup_project(tmp_path, mode="markdown")
    doc_file = _write_doc(project, "arch", _ARCH_CONTENT)
    invalidate_cache()

    checker = DocChecker("arch", str(doc_file), docs_dir=str(project / "docs"), quiet=True)
    ran_kg = checker._kg_bidirectional_coverage("F")
    assert not ran_kg, "markdown mode must not enter the KG coverage path"


# ---- R-011: dev-plan M-level coverage enforced via cf:realizes -------------

_ARCH_MODULES = """\
---
id: arch
doc_type: arch
---
# Arch

## §2 Modules

### §2.1 M-001 认证模块

认证。

### §2.2 M-002 会话模块

会话。
"""

_DEVPLAN_REALIZES_M1 = """\
---
id: dev-plan
doc_type: dev-plan
---
# Dev Plan

## §1 Tasks

### §1.1 T-001 登录任务

- **模块**: arch#§2.M-001

### §1.2 T-002 数据任务

无模块映射。
"""

_DEVPLAN_REALIZES_BOTH = """\
---
id: dev-plan
doc_type: dev-plan
---
# Dev Plan

## §1 Tasks

### §1.1 T-001 登录任务

- **模块**: arch#§2.M-001

### §1.2 T-002 会话任务

- **模块**: arch#§2.M-002
"""


def _setup_devplan_project(tmp_path: Path, devplan_md: str) -> Path:
    """Ingest a custom arch + dev-plan pair under a KG-active project."""
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg.ingest import run_migration

    project = tmp_path / "project"
    (project / ".cataforge").mkdir(parents=True)
    (project / "docs" / "arch").mkdir(parents=True)
    (project / "docs" / "dev-plan").mkdir(parents=True)
    (project / "docs" / "arch" / "arch.md").write_text(_ARCH_MODULES, encoding="utf-8")
    (project / "docs" / "dev-plan" / "dev-plan.md").write_text(devplan_md, encoding="utf-8")

    config = KGConfig(
        store_backend="oxigraph",
        db_path=project / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"arch", "dev-plan"},
    )
    handle = init_store(config, force=True)
    run_migration(handle.raw, project, config, doc_types=("arch", "dev-plan"))
    handle.raw.flush()

    (project / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"kg_active_doc_types": ["arch", "dev-plan"]}}),
        encoding="utf-8",
    )
    return project


def test_devplan_coverage_fails_when_module_unimplemented(tmp_path: Path) -> None:
    """A Module with no realizing Task fails dev-plan coverage (not a vacuous
    pass): the KG path resolves M-level coverage via `cf:realizes`."""
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

    project = _setup_devplan_project(tmp_path, _DEVPLAN_REALIZES_M1)
    invalidate_cache()

    doc_file = project / "docs" / "dev-plan" / "dev-plan.md"
    checker = DocChecker("dev-plan", str(doc_file), docs_dir=str(project / "docs"), quiet=True)
    checker.check_bidirectional_coverage()

    assert any("M-002" in e for e in checker.errors), checker.errors
    assert not any("M-001" in e for e in checker.errors), checker.errors


def test_devplan_coverage_passes_when_all_modules_realized(tmp_path: Path) -> None:
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

    project = _setup_devplan_project(tmp_path, _DEVPLAN_REALIZES_BOTH)
    invalidate_cache()

    doc_file = project / "docs" / "dev-plan" / "dev-plan.md"
    checker = DocChecker("dev-plan", str(doc_file), docs_dir=str(project / "docs"), quiet=True)
    checker.check_bidirectional_coverage()

    assert not checker.errors, checker.errors


_ARCH_MODULES_BARE_HEADINGS = """\
---
id: arch
doc_type: arch
---
# Arch

## §2 Modules

### M-001 认证模块

认证。

### M-002 会话模块

会话。
"""


def test_devplan_coverage_falls_back_to_file_scan_when_graph_has_no_modules(
    tmp_path: Path,
) -> None:
    """KG active but no upstream Module rows → the file scan must still run.

    A KG path that judges zero upstream rows is a vacuous green: it reports no
    failures AND suppresses the file fallback, so a dev-plan gap passes silently
    whenever the arch has not landed in the graph yet.
    """
    from cataforge.domain.kg import KGConfig, init_store
    from cataforge.domain.kg._dispatch import invalidate_cache
    from cataforge.domain.kg.ingest import run_migration
    from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker

    project = tmp_path / "project"
    (project / ".cataforge").mkdir(parents=True)
    (project / "docs" / "arch").mkdir(parents=True)
    (project / "docs" / "dev-plan").mkdir(parents=True)
    (project / "docs" / "arch" / "arch.md").write_text(
        _ARCH_MODULES_BARE_HEADINGS, encoding="utf-8"
    )
    (project / "docs" / "dev-plan" / "dev-plan.md").write_text(
        _DEVPLAN_REALIZES_M1, encoding="utf-8"
    )
    config = KGConfig(
        store_backend="oxigraph",
        db_path=project / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"arch", "dev-plan"},
    )
    handle = init_store(config, force=True)
    run_migration(handle.raw, project, config, doc_types=("dev-plan",))
    handle.raw.flush()
    (project / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"kg_active_doc_types": ["arch", "dev-plan"]}}),
        encoding="utf-8",
    )
    invalidate_cache()

    doc_file = project / "docs" / "dev-plan" / "dev-plan.md"
    checker = DocChecker("dev-plan", str(doc_file), docs_dir=str(project / "docs"), quiet=True)
    checker.check_bidirectional_coverage()

    assert any("M-002" in e and "上游" in e for e in checker.errors), checker.errors
