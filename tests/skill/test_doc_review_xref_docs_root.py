"""check_xref resolves cross-subdir referents via the project-global docs root.

A doc invoked with ``--docs-dir=docs/<subdir>/`` still has xref targets that
live across the whole ``docs/`` tree.
"""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.doc_review.checker import DocChecker


def _split_project(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / "docs" / "prd").mkdir(parents=True)
    (tmp_path / "docs" / "arch").mkdir(parents=True)
    (tmp_path / "docs" / "prd" / "prd-foo.md").write_text(
        "---\nid: prd-foo\nauthor: pm\nstatus: approved\ndeps: []\nconsumers: []\n---\n"
        "# PRD\n### F-001\n",
        encoding="utf-8",
    )
    return tmp_path


def test_xref_resolves_sibling_tree_via_subdir_docs_dir(tmp_path: Path) -> None:
    root = _split_project(tmp_path)
    arch = root / "docs" / "arch" / "arch-foo.md"
    arch.write_text(
        "---\nid: arch-foo\nauthor: architect\nstatus: draft\n"
        "deps: []\nconsumers: []\n---\n"
        "# ARCH\n引用上游 prd-foo#§2.F-001\n",
        encoding="utf-8",
    )
    c = DocChecker("arch", str(arch), docs_dir=str(root / "docs" / "arch"))
    c.check_xref()
    assert not any("未找到对应文件" in e for e in c.errors), c.errors


def test_xref_missing_referent_still_fails(tmp_path: Path) -> None:
    root = _split_project(tmp_path)
    arch = root / "docs" / "arch" / "arch-foo.md"
    arch.write_text(
        "---\nid: arch-foo\nauthor: architect\nstatus: draft\n"
        "deps: []\nconsumers: []\n---\n"
        "# ARCH\n引用不存在的 prd-ghost#§2.F-001\n",
        encoding="utf-8",
    )
    c = DocChecker("arch", str(arch), docs_dir=str(root / "docs" / "arch"))
    c.check_xref()
    assert any("未找到对应文件" in e and "prd-ghost" in e for e in c.errors), c.errors
