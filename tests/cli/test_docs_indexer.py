"""In-process tests for cataforge.docs.indexer.main exit semantics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cataforge.docs import indexer


def _make_project(root: Path) -> None:
    (root / ".cataforge").mkdir()
    (root / ".cataforge" / "framework.json").write_text(
        json.dumps({"version": "0.1.0"}), encoding="utf-8"
    )
    (root / "docs").mkdir()


def _write_doc(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_strict_full_rebuild_exits_3_on_orphan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_project(tmp_path)
    _write_doc(tmp_path, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    _write_doc(tmp_path, "docs/research/orphan.md", "# No front matter\n")

    rc = indexer.main(["--project-root", str(tmp_path), "--strict"])

    assert rc == 3
    err = capsys.readouterr().err
    assert "[WARN]" in err
    assert "docs/research/orphan.md" in err


def test_strict_incremental_doc_file_still_exits_3_on_unrelated_orphan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: --strict on incremental --doc-file used to skip the
    tree-wide orphan scan entirely, so a bad doc elsewhere in docs/
    silently passed the gate. The fix runs the orphan scan on every
    invocation, incremental or not."""
    _make_project(tmp_path)
    good = _write_doc(
        tmp_path, "docs/prd/good.md",
        "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n",
    )
    _write_doc(tmp_path, "docs/research/orphan.md", "# No front matter\n")

    rc = indexer.main([
        "--project-root", str(tmp_path),
        "--doc-file", str(good),
        "--strict",
    ])

    assert rc == 3, "incremental --strict must still escalate orphans elsewhere in the tree"
    err = capsys.readouterr().err
    assert "docs/research/orphan.md" in err


def test_incremental_without_strict_warns_but_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_project(tmp_path)
    good = _write_doc(
        tmp_path, "docs/prd/good.md",
        "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n",
    )
    _write_doc(tmp_path, "docs/research/orphan.md", "# No front matter\n")

    rc = indexer.main([
        "--project-root", str(tmp_path),
        "--doc-file", str(good),
    ])

    assert rc == 0
    err = capsys.readouterr().err
    assert "[WARN]" in err
    assert "docs/research/orphan.md" in err


def test_strict_full_rebuild_clean_tree_exits_zero(tmp_path: Path) -> None:
    _make_project(tmp_path)
    _write_doc(tmp_path, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")

    rc = indexer.main(["--project-root", str(tmp_path), "--strict"])

    assert rc == 0
