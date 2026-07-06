"""check_xref verifies a bare section ref (``arch#§3``) resolves to a real section.

Markdown-glob path: the target file must carry a heading for §N — numbered
(``## 2. 模块``) or §-prefixed (``## §2 模块``). A ref whose section part is
not a bare §-number (entity xref, placeholder ``§N``, URL fragment) keeps the
previous file-existence-only behaviour.
"""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker


def _md_project(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "arch.md").write_text(
        "---\nid: arch\nauthor: architect\nstatus: draft\ndeps: []\nconsumers: []\n---\n"
        "# ARCH\n\n## 1. 概览\n\n## 2. 模块\n\n### M-001 认证\n",
        encoding="utf-8",
    )
    return tmp_path


def _checker(root: Path, body: str) -> DocChecker:
    doc = root / "docs" / "dev-plan.md"
    doc.write_text(
        "---\nid: dev-plan\nauthor: tech-lead\nstatus: draft\ndeps: []\nconsumers: []\n---\n"
        f"# DEV\n\n{body}\n",
        encoding="utf-8",
    )
    return DocChecker("dev-plan", str(doc), docs_dir=str(root / "docs"), quiet=True)


def test_valid_numbered_section_ref_passes(tmp_path: Path) -> None:
    c = _checker(_md_project(tmp_path), "依赖 arch#§2 的模块划分")
    c.check_xref()
    assert not any("arch#§2" in e for e in c.errors), c.errors


def test_broken_section_ref_fails(tmp_path: Path) -> None:
    c = _checker(_md_project(tmp_path), "依赖 arch#§9 的模块划分")
    c.check_xref()
    assert any("arch#§9" in e for e in c.errors), c.errors


def test_section_prefixed_heading_style_passes(tmp_path: Path) -> None:
    root = _md_project(tmp_path)
    (root / "docs" / "prd.md").write_text(
        "---\nid: prd\nauthor: pm\nstatus: draft\ndeps: []\nconsumers: []\n---\n"
        "# PRD\n\n## §1 概览\n\n## §2 功能\n",
        encoding="utf-8",
    )
    c = _checker(root, "上游 prd#§2 定义的功能")
    c.check_xref()
    assert not any("prd#§2" in e for e in c.errors), c.errors


def test_placeholder_section_letter_not_checked(tmp_path: Path) -> None:
    c = _checker(_md_project(tmp_path), "引用格式形如 arch#§N")
    c.check_xref()
    assert not c.errors, c.errors


def test_dotted_subsection_ref_resolves(tmp_path: Path) -> None:
    root = _md_project(tmp_path)
    (root / "docs" / "arch.md").write_text(
        "---\nid: arch\nauthor: architect\nstatus: draft\ndeps: []\nconsumers: []\n---\n"
        "# ARCH\n\n## 3. 接口\n\n### 3.2 内部接口\n",
        encoding="utf-8",
    )
    ok = _checker(root, "见 arch#§3.2 内部接口")
    ok.check_xref()
    assert not any("arch#§3.2" in e for e in ok.errors), ok.errors

    broken = _checker(root, "见 arch#§3.9 不存在小节")
    broken.check_xref()
    assert any("arch#§3.9" in e for e in broken.errors), broken.errors


def test_url_fragment_not_checked(tmp_path: Path) -> None:
    c = _checker(
        _md_project(tmp_path),
        "见 https://example.com/page#section-3 与 http://x#§9 外部链接",
    )
    c.check_xref()
    assert not c.errors, c.errors
