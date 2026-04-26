"""In-process tests for cataforge.docs.indexer.main exit semantics
plus the reverse-orphan / stale-entry detection added in PR #75."""

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


def test_find_stale_index_entries_detects_disk_deletion(tmp_path: Path) -> None:
    _make_project(tmp_path)
    good = _write_doc(
        tmp_path, "docs/prd/good.md",
        "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n",
    )
    indexer.main(["--project-root", str(tmp_path)])

    good.unlink()

    stale = indexer.find_stale_index_entries(str(tmp_path))
    assert len(stale) == 1
    doc_id, rel = stale[0]
    assert doc_id == "prd-good"
    assert rel.endswith("good.md")


def test_find_stale_index_entries_clean_when_index_absent(tmp_path: Path) -> None:
    _make_project(tmp_path)
    assert indexer.find_stale_index_entries(str(tmp_path)) == []


def test_find_stale_index_entries_clean_when_files_present(tmp_path: Path) -> None:
    _make_project(tmp_path)
    _write_doc(tmp_path, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    indexer.main(["--project-root", str(tmp_path)])

    assert indexer.find_stale_index_entries(str(tmp_path)) == []


def test_strict_incremental_warns_on_stale_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Incremental --strict run must escalate when an index entry's
    file_path is missing on disk (the symmetric case to orphan docs)."""
    _make_project(tmp_path)
    a = _write_doc(tmp_path, "docs/prd/a.md", "---\nid: prd-a\ndoc_type: prd\n---\n# A\n")
    b = _write_doc(tmp_path, "docs/prd/b.md", "---\nid: prd-b\ndoc_type: prd\n---\n# B\n")
    indexer.main(["--project-root", str(tmp_path)])

    b.unlink()

    rc = indexer.main([
        "--project-root", str(tmp_path),
        "--doc-file", str(a),
        "--strict",
    ])

    assert rc == 3, "stale index entry must trip --strict on incremental run"
    err = capsys.readouterr().err
    assert "prd-b" in err
