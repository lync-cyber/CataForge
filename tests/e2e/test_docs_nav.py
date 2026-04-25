"""End-to-end tests for `cataforge docs` — real wheel install, real CLI subprocess.

These tests prove the doc-nav skill's load-section instruction actually works
when an Agent invokes ``cataforge docs load`` from a shell, not just when the
loader module is imported in-process. Migration tool is exercised against a
realistic legacy NAV-INDEX.md layout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .conftest import run_cataforge


@pytest.fixture
def project_with_doc(tmp_path: Path) -> Path:
    """Minimal project: framework.json + one indexable PRD."""
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps({"version": "0.1.0"}), encoding="utf-8"
    )
    (tmp_path / "docs" / "prd").mkdir(parents=True)
    (tmp_path / "docs" / "prd" / "prd-foo-v1.md").write_text(
        "---\nid: prd-foo-v1\ndoc_type: prd\n---\n\n"
        "# PRD: Foo\n\n"
        "## 1. Overview\n\nFoo is a sample app.\n\n"
        "## 2. Features\n\n"
        "### F-001 Login\n\n用户通过邮箱密码登录。\n\n"
        "### F-002 Logout\n\n用户登出后清空会话。\n",
        encoding="utf-8",
    )
    return tmp_path


def test_docs_load_extracts_section_via_real_cli(
    cataforge_venv: Path, project_with_doc: Path
) -> None:
    """End-to-end golden path: index → load → assert section content in stdout."""
    rc_index = run_cataforge(cataforge_venv, "docs", "index", cwd=project_with_doc)
    assert rc_index.returncode == 0, rc_index.stderr

    rc_load = run_cataforge(
        cataforge_venv, "docs", "load", "prd#§2.F-001", cwd=project_with_doc
    )
    assert rc_load.returncode == 0, rc_load.stderr
    assert "=== prd#§2.F-001 ===" in rc_load.stdout
    assert "用户通过邮箱密码登录" in rc_load.stdout


def test_docs_load_json_flag_emits_parseable_array(
    cataforge_venv: Path, project_with_doc: Path
) -> None:
    run_cataforge(cataforge_venv, "docs", "index", cwd=project_with_doc)
    rc = run_cataforge(
        cataforge_venv, "docs", "load", "--json", "prd#§1", "prd#§2.F-002",
        cwd=project_with_doc,
    )
    assert rc.returncode == 0, rc.stderr
    payload = json.loads(rc.stdout)
    assert isinstance(payload, list) and len(payload) == 2
    by_ref = {item["ref"]: item for item in payload}
    assert by_ref["prd#§1"]["status"] == "ok"
    assert "Foo is a sample app" in by_ref["prd#§1"]["content"]
    assert by_ref["prd#§2.F-002"]["status"] == "ok"
    assert by_ref["prd#§2.F-002"]["line_start"] >= 1


def test_docs_load_budget_routes_overflow_to_stderr(
    cataforge_venv: Path, project_with_doc: Path
) -> None:
    run_cataforge(cataforge_venv, "docs", "index", cwd=project_with_doc)
    # est_tokens for tiny sections is at most a few dozen — budget=1 forces
    # every ref to defer.
    rc = run_cataforge(
        cataforge_venv, "docs", "load", "--budget", "1",
        "prd#§1", "prd#§2.F-001",
        cwd=project_with_doc,
    )
    assert rc.returncode == 0, rc.stderr
    assert "[DEFERRED]" in rc.stderr
    assert "prd#§1" in rc.stderr
    assert "prd#§2.F-001" in rc.stderr
    # No section content should be emitted to stdout (everything was deferred)
    assert "=== prd#§" not in rc.stdout


def test_docs_load_failed_ref_exits_2_with_stderr(
    cataforge_venv: Path, project_with_doc: Path
) -> None:
    run_cataforge(cataforge_venv, "docs", "index", cwd=project_with_doc)
    rc = run_cataforge(
        cataforge_venv, "docs", "load", "prd#§99",
        cwd=project_with_doc, check=False,
    )
    assert rc.returncode == 2
    assert "[ERROR]" in rc.stderr
    assert "prd#§99" in rc.stderr


def test_docs_migrate_nav_archives_deletes_and_rebuilds(
    cataforge_venv: Path, project_with_doc: Path
) -> None:
    """End-to-end migration: NAV-INDEX.md → archived + .doc-index.json present."""
    nav = project_with_doc / "docs" / "NAV-INDEX.md"
    nav.write_text(
        "# NAV-INDEX: foo\n\n"
        "## 文档总览\n\n"
        "| Doc ID | 文件路径 | 状态 | 分卷 | 章节数 |\n"
        "|--------|----------|------|------|--------|\n"
        "| prd | docs/prd/prd-foo-v1.md | draft | 1 | 2 |\n",
        encoding="utf-8",
    )

    rc = run_cataforge(
        cataforge_venv, "docs", "migrate-nav", cwd=project_with_doc
    )
    assert rc.returncode == 0, rc.stderr

    assert not nav.exists(), "NAV-INDEX.md should be removed after migration"

    archive_dir = project_with_doc / ".cataforge" / ".archive"
    assert archive_dir.is_dir(), "archive directory must exist"
    archived = list(archive_dir.glob("NAV-INDEX-*.md"))
    assert len(archived) == 1, f"expected one archive file, got {archived}"

    idx = project_with_doc / "docs" / ".doc-index.json"
    assert idx.is_file(), ".doc-index.json must be rebuilt"
    idx_data = json.loads(idx.read_text(encoding="utf-8"))
    assert idx_data["documents"], "rebuilt index must contain documents"

    # And the loader should now succeed against the rebuilt index.
    rc_load = run_cataforge(
        cataforge_venv, "docs", "load", "prd#§1", cwd=project_with_doc
    )
    assert rc_load.returncode == 0, rc_load.stderr
    assert "Foo is a sample app" in rc_load.stdout


def test_docs_migrate_nav_dry_run_preserves_files(
    cataforge_venv: Path, project_with_doc: Path
) -> None:
    nav = project_with_doc / "docs" / "NAV-INDEX.md"
    nav.write_text(
        "## 文档总览\n\n| Doc ID | 文件路径 |\n|--|--|\n| prd | docs/prd/prd-foo-v1.md |\n",
        encoding="utf-8",
    )

    rc = run_cataforge(
        cataforge_venv, "docs", "migrate-nav", "--dry-run", cwd=project_with_doc
    )
    assert rc.returncode == 0, rc.stderr
    assert nav.exists(), "dry-run must not delete NAV-INDEX.md"
    assert not (project_with_doc / ".cataforge" / ".archive").exists()
    assert not (project_with_doc / "docs" / ".doc-index.json").exists()
    assert "DRY-RUN" in rc.stdout


def test_docs_load_uses_external_doc_type_map(
    cataforge_venv: Path, tmp_path: Path
) -> None:
    """Custom doc_type registered in framework.json must be resolvable."""
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps({
            "version": "0.1.0",
            "docs": {"doc_types": {"runbook": "runbooks"}},
        }),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "runbooks").mkdir(parents=True)
    (tmp_path / "docs" / "runbooks" / "runbook-deploy-v1.md").write_text(
        "---\nid: runbook-deploy-v1\ndoc_type: runbook\n---\n\n"
        "# Runbook: deploy\n\n## 1. Prereqs\n\nKubectl 1.30+\n",
        encoding="utf-8",
    )

    run_cataforge(cataforge_venv, "docs", "index", cwd=tmp_path)
    rc = run_cataforge(
        cataforge_venv, "docs", "load", "runbook#§1", cwd=tmp_path
    )
    assert rc.returncode == 0, rc.stderr
    assert "Kubectl 1.30+" in rc.stdout
