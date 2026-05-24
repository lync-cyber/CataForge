"""Tests for content_hash, dep_hashes, and stale deps detection (Batch A)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cataforge.cli.docs_cmd import docs_validate
from cataforge.docs import indexer

_PRD_FM = "---\nid: prd-foo\ndoc_type: prd\n---\n"
_ARCH_FM = (
    "---\nid: arch-foo\ndoc_type: arch\n"
    "deps: [prd-foo]\n---\n# ARCH\n"
)


def _make_project(tmp_path: Path) -> Path:
    cf = tmp_path / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime_api_version": "1.0"}),
        encoding="utf-8",
    )
    return tmp_path


def _write_doc(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _read_index(root: Path) -> dict:
    idx_path = root / "docs" / ".doc-index.json"
    return json.loads(idx_path.read_text(encoding="utf-8"))


# ---- content_hash basics ----


def test_content_hash_present_in_index(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    _write_doc(
        root, "docs/prd/prd-foo.md",
        _PRD_FM + "# PRD\nContent here\n",
    )
    indexer.main(["--project-root", str(root)])
    idx = _read_index(root)
    assert "content_hash" in idx["documents"]["prd-foo"]
    assert len(idx["documents"]["prd-foo"]["content_hash"]) == 8


def test_content_hash_changes_when_body_changes(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    _write_doc(
        root, "docs/prd/prd-foo.md",
        _PRD_FM + "# PRD\nVersion 1\n",
    )
    indexer.main(["--project-root", str(root)])
    hash_v1 = _read_index(root)["documents"]["prd-foo"]["content_hash"]

    _write_doc(
        root, "docs/prd/prd-foo.md",
        _PRD_FM + "# PRD\nVersion 2\n",
    )
    indexer.main(["--project-root", str(root)])
    hash_v2 = _read_index(root)["documents"]["prd-foo"]["content_hash"]

    assert hash_v1 != hash_v2


def test_content_hash_stable_for_same_body(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    body = _PRD_FM + "# PRD\nStable content\n"
    _write_doc(root, "docs/prd/prd-foo.md", body)
    indexer.main(["--project-root", str(root)])
    hash_1 = _read_index(root)["documents"]["prd-foo"]["content_hash"]

    indexer.main(["--project-root", str(root)])
    hash_2 = _read_index(root)["documents"]["prd-foo"]["content_hash"]

    assert hash_1 == hash_2


# ---- dep_hashes ----


def test_dep_hashes_recorded_for_downstream_doc(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    _write_doc(
        root, "docs/prd/prd-foo.md", _PRD_FM + "# PRD\n",
    )
    _write_doc(root, "docs/arch/arch-foo.md", _ARCH_FM)
    indexer.main(["--project-root", str(root)])
    idx = _read_index(root)
    arch_entry = idx["documents"]["arch-foo"]
    assert "dep_hashes" in arch_entry
    assert "prd-foo" in arch_entry["dep_hashes"]
    prd_hash = idx["documents"]["prd-foo"]["content_hash"]
    assert arch_entry["dep_hashes"]["prd-foo"] == prd_hash


def test_dep_hashes_absent_when_no_deps(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    _write_doc(
        root, "docs/prd/prd-foo.md", _PRD_FM + "# PRD\n",
    )
    indexer.main(["--project-root", str(root)])
    idx = _read_index(root)
    assert "dep_hashes" not in idx["documents"]["prd-foo"]


# ---- stale deps detection ----


def test_stale_deps_detected_when_upstream_changes(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    _write_doc(
        root, "docs/prd/prd-foo.md",
        _PRD_FM + "# PRD\nOriginal\n",
    )
    _write_doc(root, "docs/arch/arch-foo.md", _ARCH_FM)
    indexer.main(["--project-root", str(root)])

    _write_doc(
        root, "docs/prd/prd-foo.md",
        _PRD_FM + "# PRD\nRevised with F-004\n",
    )
    indexer.main([
        "--project-root", str(root),
        "--doc-file", "docs/prd/prd-foo.md",
    ])

    stale = indexer.find_stale_deps(str(root))
    assert len(stale) == 1
    assert stale[0]["doc_id"] == "arch-foo"
    assert stale[0]["upstream_id"] == "prd-foo"


def test_stale_deps_clean_when_both_rebuilt(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    _write_doc(
        root, "docs/prd/prd-foo.md",
        _PRD_FM + "# PRD\nOriginal\n",
    )
    _write_doc(root, "docs/arch/arch-foo.md", _ARCH_FM)
    indexer.main(["--project-root", str(root)])

    stale = indexer.find_stale_deps(str(root))
    assert stale == []


def test_stale_deps_clean_after_full_rebuild(tmp_path: Path) -> None:
    root = _make_project(tmp_path)
    _write_doc(
        root, "docs/prd/prd-foo.md",
        _PRD_FM + "# PRD\nOriginal\n",
    )
    _write_doc(root, "docs/arch/arch-foo.md", _ARCH_FM)
    indexer.main(["--project-root", str(root)])

    _write_doc(
        root, "docs/prd/prd-foo.md",
        _PRD_FM + "# PRD\nChanged\n",
    )
    indexer.main(["--project-root", str(root)])

    stale = indexer.find_stale_deps(str(root))
    assert stale == []


# ---- CLI integration ----


def test_validate_shows_stale_deps_as_warn(
    tmp_path: Path, monkeypatch,
) -> None:
    root = _make_project(tmp_path)
    _write_doc(
        root, "docs/prd/prd-foo.md",
        _PRD_FM + "# PRD\nOriginal\n",
    )
    _write_doc(root, "docs/arch/arch-foo.md", _ARCH_FM)
    indexer.main(["--project-root", str(root)])

    _write_doc(
        root, "docs/prd/prd-foo.md",
        _PRD_FM + "# PRD\nRevised\n",
    )
    indexer.main([
        "--project-root", str(root),
        "--doc-file", "docs/prd/prd-foo.md",
    ])

    monkeypatch.chdir(root)
    result = CliRunner().invoke(docs_validate, [])
    assert result.exit_code == 0
    assert "stale dep" in result.output.lower()
