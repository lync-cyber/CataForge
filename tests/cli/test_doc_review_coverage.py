"""Tests for bidirectional coverage check in doc-review Layer 1 (Batch B)."""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# ---- ARCH must cover all F-NNN from PRD ----


def test_arch_missing_feature_coverage(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    _write(
        tmp_path,
        "docs/prd/prd-foo.md",
        "---\nid: prd-foo\ndoc_type: prd\n---\n# PRD\n"
        "### F-001: Login\n### F-002: Signup\n### F-003: Export\n",
    )
    arch_path = _write(
        tmp_path,
        "docs/arch/arch-foo.md",
        "---\nid: arch-foo\ndoc_type: arch\ndeps: [prd-foo]\n---\n"
        "# ARCH\n[NAV]\n- §1 Overview\n- §2 Modules\n[/NAV]\n"
        "## 1. Overview\nOverview\n"
        "## 2. Modules\n### M-001: Auth\nCovers F-001, F-002\n",
    )
    checker = DocChecker("arch", str(arch_path), str(docs), quiet=True)
    checker.check_bidirectional_coverage()
    assert any("F-003" in e for e in checker.errors)


def test_arch_full_feature_coverage(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    _write(
        tmp_path,
        "docs/prd/prd-foo.md",
        "---\nid: prd-foo\ndoc_type: prd\n---\n# PRD\n### F-001: Login\n### F-002: Signup\n",
    )
    arch_path = _write(
        tmp_path,
        "docs/arch/arch-foo.md",
        "---\nid: arch-foo\ndoc_type: arch\ndeps: [prd-foo]\n---\n"
        "# ARCH\n## 2. Modules\n"
        "### M-001: Auth\nCovers F-001\n"
        "### M-002: Reg\nCovers F-002\n",
    )
    checker = DocChecker("arch", str(arch_path), str(docs), quiet=True)
    checker.check_bidirectional_coverage()
    assert not checker.errors


# ---- DEV-PLAN must cover all M-NNN from ARCH ----


def test_dev_plan_missing_module_coverage(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    _write(
        tmp_path,
        "docs/arch/arch-foo.md",
        "---\nid: arch-foo\ndoc_type: arch\n---\n# ARCH\n"
        "### M-001: Auth\n### M-002: Data\n### M-003: Export\n",
    )
    plan_path = _write(
        tmp_path,
        "docs/dev-plan/dev-plan-foo.md",
        "---\nid: dev-plan-foo\ndoc_type: dev-plan\ndeps: [arch-foo]\n---\n"
        "# DEV-PLAN\n## 3. Tasks\n"
        "### T-001: Login\nM-001\n"
        "### T-002: Data\nM-002\n",
    )
    checker = DocChecker("dev-plan", str(plan_path), str(docs), quiet=True)
    checker.check_bidirectional_coverage()
    assert any("M-003" in e for e in checker.errors)


# ---- UI-SPEC must cover all F-NNN from PRD ----


def test_ui_spec_missing_feature_coverage(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    _write(
        tmp_path,
        "docs/prd/prd-foo.md",
        "---\nid: prd-foo\ndoc_type: prd\n---\n# PRD\n### F-001: Login\n### F-002: Dashboard\n",
    )
    ui_path = _write(
        tmp_path,
        "docs/ui-spec/ui-spec-foo.md",
        "---\nid: ui-spec-foo\ndoc_type: ui-spec\ndeps: [prd-foo]\n---\n"
        "# UI-SPEC\n## 2. Components\n"
        "### C-001: LoginForm\nF-001\n",
    )
    checker = DocChecker("ui-spec", str(ui_path), str(docs), quiet=True)
    checker.check_bidirectional_coverage()
    assert any("F-002" in e for e in checker.errors)


# ---- --docs-dir is a doc_type subdir, upstream is project-global ----


def _subdir_project(tmp_path: Path) -> Path:
    """Project whose arch doc is invoked with --docs-dir=docs/arch/.

    Upstream PRD lives at the project-global docs/prd/ — the coverage scan
    must not be scoped to the subdir passed as docs_dir.
    """
    (tmp_path / ".cataforge").mkdir()
    _write(
        tmp_path,
        "docs/prd/prd-foo.md",
        "---\nid: prd-foo\ndoc_type: prd\n---\n# PRD\n"
        "### F-001: Login\n### F-002: Signup\n### F-003: Export\n",
    )
    return tmp_path


def test_arch_missing_coverage_via_subdir_docs_dir(tmp_path: Path) -> None:
    root = _subdir_project(tmp_path)
    arch_path = _write(
        root,
        "docs/arch/arch-foo.md",
        "---\nid: arch-foo\ndoc_type: arch\ndeps: [prd-foo]\n---\n"
        "# ARCH\n## 2. Modules\n### M-001: Auth\nCovers F-001, F-002\n",
    )
    checker = DocChecker("arch", str(arch_path), str(root / "docs" / "arch"), quiet=True)
    checker.check_bidirectional_coverage()
    assert any("F-003" in e for e in checker.errors), checker.errors


def test_arch_full_coverage_via_subdir_docs_dir(tmp_path: Path) -> None:
    root = _subdir_project(tmp_path)
    arch_path = _write(
        root,
        "docs/arch/arch-foo.md",
        "---\nid: arch-foo\ndoc_type: arch\ndeps: [prd-foo]\n---\n"
        "# ARCH\n## 2. Modules\n### M-001\nCovers F-001, F-002, F-003\n",
    )
    checker = DocChecker("arch", str(arch_path), str(root / "docs" / "arch"), quiet=True)
    checker.check_bidirectional_coverage()
    assert not checker.errors, checker.errors


# ---- No upstream docs found → no error ----


def test_coverage_no_upstream_is_noop(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    arch_path = _write(
        tmp_path,
        "docs/arch/arch-foo.md",
        "---\nid: arch-foo\ndoc_type: arch\n---\n# ARCH\n## 2. Modules\n",
    )
    checker = DocChecker("arch", str(arch_path), str(docs), quiet=True)
    checker.check_bidirectional_coverage()
    assert not checker.errors


# ---- PRD (no upstream) → no check ----


def test_coverage_not_applicable_for_prd(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    prd_path = _write(
        tmp_path,
        "docs/prd/prd-foo.md",
        "---\nid: prd-foo\ndoc_type: prd\n---\n# PRD\n### F-001: Login\n",
    )
    checker = DocChecker("prd", str(prd_path), str(docs), quiet=True)
    checker.check_bidirectional_coverage()
    assert not checker.errors
