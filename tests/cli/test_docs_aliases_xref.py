"""Tests for aliases / prefix-fallback ambiguity / xref validation /
frontmatter `required_sections` fallback — added with the doc-review
resolver and template-fallback fixes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cataforge.cli.docs_cmd import docs_validate
from cataforge.docs import indexer, loader


@pytest.fixture(autouse=True)
def reset_caches():
    loader._INDEX_CACHE = None
    loader._INDEX_CACHE_ROOT = None
    loader._DOC_TYPE_MAP_CACHE.clear()
    yield
    loader._INDEX_CACHE = None
    loader._INDEX_CACHE_ROOT = None
    loader._DOC_TYPE_MAP_CACHE.clear()


def _make_project(root: Path) -> Path:
    (root / ".cataforge").mkdir()
    (root / ".cataforge" / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime_api_version": "1.0"}),
        encoding="utf-8",
    )
    (root / "docs").mkdir()
    return root


def _write_doc(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# --- aliases ---------------------------------------------------------------


def test_alias_resolves_to_full_doc_id(tmp_path: Path) -> None:
    _make_project(tmp_path)
    _write_doc(
        tmp_path, "docs/arch/arch-wechat-data.md",
        '---\nid: arch-wechat-data\ndoc_type: arch\naliases: ["arch-data"]\n---\n'
        "# arch\n\n## 4. 数据\n\n### E-002 模型\n字段 A\n",
    )
    indexer.main(["--project-root", str(tmp_path)])

    content = loader.extract("arch-data#§4.E-002", str(tmp_path))
    assert "字段 A" in content


def test_aliases_recorded_in_index_top_level(tmp_path: Path) -> None:
    _make_project(tmp_path)
    _write_doc(
        tmp_path, "docs/arch/arch-foo-data.md",
        '---\nid: arch-foo-data\ndoc_type: arch\naliases: ["arch-data", "data"]\n---\n# x\n',
    )
    indexer.main(["--project-root", str(tmp_path)])
    idx = json.loads((tmp_path / "docs" / ".doc-index.json").read_text(encoding="utf-8"))
    assert idx["aliases"]["arch-data"] == "arch-foo-data"
    assert idx["aliases"]["data"] == "arch-foo-data"


def test_alias_conflict_first_claim_wins_and_reported(tmp_path: Path) -> None:
    _make_project(tmp_path)
    # Two docs claim the same alias `arch-data`. First claim wins; second
    # surfaces as an alias_conflict.
    _write_doc(
        tmp_path, "docs/arch/arch-aaa-data.md",
        '---\nid: arch-aaa-data\ndoc_type: arch\naliases: ["arch-data"]\n---\n# a\n',
    )
    _write_doc(
        tmp_path, "docs/arch/arch-bbb-data.md",
        '---\nid: arch-bbb-data\ndoc_type: arch\naliases: ["arch-data"]\n---\n# b\n',
    )
    indexer.main(["--project-root", str(tmp_path)])
    idx = json.loads((tmp_path / "docs" / ".doc-index.json").read_text(encoding="utf-8"))
    # First (sorted) wins
    assert idx["aliases"]["arch-data"] == "arch-aaa-data"
    conflicts = idx.get("alias_conflicts", [])
    assert any(c["alias"] == "arch-data" and c["claimed_by"] == "arch-bbb-data"
               for c in conflicts)


def test_alias_shadowed_by_real_doc_id_is_rejected(tmp_path: Path) -> None:
    _make_project(tmp_path)
    _write_doc(
        tmp_path, "docs/arch/arch.md",
        '---\nid: arch\ndoc_type: arch\n---\n# arch\n',
    )
    _write_doc(
        tmp_path, "docs/arch/arch-foo.md",
        '---\nid: arch-foo\ndoc_type: arch\naliases: ["arch"]\n---\n# foo\n',
    )
    indexer.main(["--project-root", str(tmp_path)])
    idx = json.loads((tmp_path / "docs" / ".doc-index.json").read_text(encoding="utf-8"))
    # The alias must not shadow the real doc_id
    assert "arch" not in idx.get("aliases", {})
    assert any(c["alias"] == "arch" for c in idx.get("alias_conflicts", []))


# --- prefix-fallback ambiguity --------------------------------------------


def test_prefix_fallback_unique_match_resolves(tmp_path: Path) -> None:
    """Single match still resolves — backwards compat with the old behavior."""
    _make_project(tmp_path)
    _write_doc(
        tmp_path, "docs/prd/prd-foo-v1.md",
        "---\nid: prd-foo-v1\ndoc_type: prd\n---\n"
        "# x\n\n## 1. Overview\n内容\n",
    )
    indexer.main(["--project-root", str(tmp_path)])
    content = loader.extract("prd#§1", str(tmp_path))
    assert "内容" in content


def test_prefix_fallback_multiple_matches_raises(tmp_path: Path) -> None:
    _make_project(tmp_path)
    _write_doc(
        tmp_path, "docs/prd/prd-foo-v1.md",
        "---\nid: prd-foo-v1\ndoc_type: prd\n---\n# foo\n\n## 1. X\nA\n",
    )
    _write_doc(
        tmp_path, "docs/prd/prd-bar-v1.md",
        "---\nid: prd-bar-v1\ndoc_type: prd\n---\n# bar\n\n## 1. Y\nB\n",
    )
    indexer.main(["--project-root", str(tmp_path)])
    with pytest.raises(loader.AmbiguousRefError, match="多个文档"):
        loader.extract("prd#§1", str(tmp_path))


# --- xref validation -------------------------------------------------------


def test_validate_docs_reports_unresolvable_dep(tmp_path: Path, monkeypatch) -> None:
    root = _make_project(tmp_path)
    _write_doc(
        root, "docs/arch/arch-foo.md",
        '---\nid: arch-foo\ndoc_type: arch\n'
        'deps: ["nonexistent#§1"]\n'
        '---\n# x\n\n## 1. X\nA\n',
    )
    indexer.main(["--project-root", str(root)])

    monkeypatch.chdir(root)
    result = CliRunner().invoke(docs_validate, [])
    assert result.exit_code == 3
    out = result.output + (result.stderr_bytes or b"").decode("utf-8", errors="replace")
    assert "nonexistent#§1" in out or "未找到引用目标" in out


def test_validate_docs_alias_resolves_dep(tmp_path: Path, monkeypatch) -> None:
    """A dep using an alias must resolve cleanly through validate_docs."""
    root = _make_project(tmp_path)
    _write_doc(
        root, "docs/arch/arch-foo-data.md",
        '---\nid: arch-foo-data\ndoc_type: arch\naliases: ["arch-data"]\n---\n'
        "# data\n\n## 4. 数据\n\n### E-002 模型\n字段\n",
    )
    _write_doc(
        root, "docs/ui-spec/ui-spec-foo-theme-04.md",
        '---\nid: ui-spec-foo-theme-04\ndoc_type: ui-spec\n'
        'volume_type: theme\n'
        'deps: ["arch-data#§4.E-002"]\n'
        'split_from: ui-spec-foo\n'
        'required_sections:\n  - "## 4. 主题"\n'
        '---\n# theme\n\n## 4. 主题\n内容\n',
    )
    indexer.main(["--project-root", str(root)])

    monkeypatch.chdir(root)
    result = CliRunner().invoke(docs_validate, [])
    assert result.exit_code == 0, result.output
