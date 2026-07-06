"""project_root_from_docs_dir — resolve a project root from any docs directory."""

from __future__ import annotations

from pathlib import Path

from cataforge.core.paths import project_root_from_docs_dir


def _project(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    return tmp_path


def test_docs_dir_one_level_below_root(tmp_path: Path) -> None:
    root = _project(tmp_path)
    docs = root / "docs"
    docs.mkdir()
    assert project_root_from_docs_dir(docs) == root


def test_docs_dir_is_root_itself(tmp_path: Path) -> None:
    root = _project(tmp_path)
    assert project_root_from_docs_dir(root) == root


def test_doc_type_subdir_two_levels_below_root(tmp_path: Path) -> None:
    root = _project(tmp_path)
    subdir = root / "docs" / "arch"
    subdir.mkdir(parents=True)
    assert project_root_from_docs_dir(subdir) == root


def test_no_cataforge_returns_none(tmp_path: Path) -> None:
    docs = tmp_path / "docs" / "arch"
    docs.mkdir(parents=True)
    assert project_root_from_docs_dir(docs) is None
