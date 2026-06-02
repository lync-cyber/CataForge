"""Tests for `cataforge docs validate` and the doctor warn-on-missing-index path."""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.domain.docs import indexer
from cataforge.interface.cli.docs_cmd import docs_validate
from cataforge.interface.cli.doctor_cmd import doctor_command
from tests.cli.conftest import invoke_under_group


def _minimal_project(tmp_path: Path) -> Path:
    from tests.cli.conftest import populate_required_source_assets

    cf = tmp_path / ".cataforge"
    cf.mkdir()
    (cf / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime_api_version": "1.0"}),
        encoding="utf-8",
    )
    populate_required_source_assets(cf)
    return tmp_path


def _write_doc(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_docs_validate_clean_index_exits_zero(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    indexer.main(["--project-root", str(root)])

    monkeypatch.chdir(root)
    result = invoke_under_group(docs_validate, [])
    assert result.exit_code == 0
    assert "0 orphans" in result.output


def test_docs_validate_orphan_exits_3(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    indexer.main(["--project-root", str(root)])
    _write_doc(root, "docs/research/orphan.md", "# No front matter\n")

    monkeypatch.chdir(root)
    result = invoke_under_group(docs_validate, [])
    assert result.exit_code == 3
    assert "orphan" in result.output.lower()


def test_docs_validate_stale_entry_exits_3(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    good = _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    indexer.main(["--project-root", str(root)])
    good.unlink()

    monkeypatch.chdir(root)
    result = invoke_under_group(docs_validate, [])
    assert result.exit_code == 3
    assert "stale" in result.output.lower()


def test_docs_validate_no_index_exits_2(tmp_path: Path, monkeypatch) -> None:
    """`docs validate` is a no-network CI gate; absence of the index is a
    distinct error class (exit 2) from validation failures (exit 3)."""
    root = _minimal_project(tmp_path)
    (root / "docs").mkdir()

    monkeypatch.chdir(root)
    result = invoke_under_group(docs_validate, [])
    assert result.exit_code == 2


def test_doctor_warns_when_index_missing_but_docs_present(tmp_path: Path, monkeypatch) -> None:
    """Pre-PR-#75 doctor silently returned 0 here, hiding the
    opt-in-or-not signal from first-time users."""
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/architecture/overview.md", "# Overview\n")

    monkeypatch.chdir(root)
    result = invoke_under_group(doctor_command, [])
    assert result.exit_code == 0  # WARN is non-blocking
    assert "WARN" in result.output
    assert "cataforge docs index" in result.output


def test_doctor_silent_when_docs_dir_empty(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    (root / "docs").mkdir()

    monkeypatch.chdir(root)
    result = invoke_under_group(doctor_command, [])
    assert result.exit_code == 0
    assert "WARN" not in result.output


def test_docignore_excludes_orphan_from_failure(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    indexer.main(["--project-root", str(root)])
    _write_doc(root, "docs/guide/published.md", "# No front matter\n")
    _write_doc(root, "docs/.docignore", "guide/\n")

    monkeypatch.chdir(root)
    result = invoke_under_group(docs_validate, [])
    assert result.exit_code == 0
    assert "1 doc(s) excluded by docs/.docignore" in result.output


def test_docignore_does_not_hide_unlisted_orphan(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    indexer.main(["--project-root", str(root)])
    _write_doc(root, "docs/guide/published.md", "# excluded\n")
    _write_doc(root, "docs/research/real-orphan.md", "# still an orphan\n")
    _write_doc(root, "docs/.docignore", "guide/\n")

    monkeypatch.chdir(root)
    result = invoke_under_group(docs_validate, [])
    assert result.exit_code == 3
    assert "research/real-orphan.md" in result.output
    assert "guide/published.md" not in result.output


def test_docignore_split_in_validate_result(tmp_path: Path) -> None:
    root = _minimal_project(tmp_path)
    _write_doc(root, "docs/reference/api.md", "# published\n")
    _write_doc(root, "docs/research/orphan.md", "# real orphan\n")
    _write_doc(root, "docs/.docignore", "# comment\n\nreference/\n")

    result = indexer.validate_docs(str(root))
    assert result["orphans"] == ["docs/research/orphan.md"]
    assert result["ignored"] == ["docs/reference/api.md"]


def test_doctor_reports_stale_index_entries(tmp_path: Path, monkeypatch) -> None:
    root = _minimal_project(tmp_path)
    good = _write_doc(root, "docs/prd/good.md", "---\nid: prd-good\ndoc_type: prd\n---\n# Good\n")
    indexer.main(["--project-root", str(root)])
    good.unlink()

    monkeypatch.chdir(root)
    result = invoke_under_group(doctor_command, [])
    assert result.exit_code == 1
    assert "stale" in result.output.lower()
    assert "prd-good" in result.output
