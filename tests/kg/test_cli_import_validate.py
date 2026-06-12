"""`cataforge kg import` + `validate` + `export` CLI smoke."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "kg-vertical-slice"


def _cli():
    from cataforge.interface.cli.main import _register_commands, cli

    _register_commands()
    return cli


def _doc_only_project(tmp_path: Path) -> Path:
    project = tmp_path / "doc-only"
    (project / ".cataforge").mkdir(parents=True)
    (project / "docs").mkdir()
    (project / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"strategy": "doc-only", "kg_active_doc_types": ["prd", "arch"]}}),
        encoding="utf-8",
    )
    return project


def test_kg_import_doc_only_is_noop(tmp_path: Path) -> None:
    from cataforge.domain.kg._dispatch import invalidate_cache

    invalidate_cache()
    project = _doc_only_project(tmp_path)
    result = CliRunner().invoke(
        _cli(),
        ["kg", "import", "--project-root", str(project), "--backend", "memory"],
    )
    invalidate_cache()
    assert result.exit_code == 0, result.output
    assert "doc-only" in result.output
    assert not (project / ".cataforge" / "kg" / "store").exists()


def test_kg_reconcile_doc_only_is_noop_despite_store(tmp_path: Path) -> None:
    """A stray store on a doc-only project must not be reconciled."""
    from cataforge.domain.kg._dispatch import invalidate_cache

    invalidate_cache()
    project = _doc_only_project(tmp_path)
    db = project / ".cataforge" / "kg" / "store"
    init = CliRunner().invoke(_cli(), ["kg", "init", "--db-path", str(db), "--backend", "oxigraph"])
    assert init.exit_code == 0, init.output

    result = CliRunner().invoke(
        _cli(),
        ["kg", "reconcile", "--project-root", str(project), "--db-path", str(db)],
    )
    invalidate_cache()
    assert result.exit_code == 0, result.output
    assert "doc-only" in result.output


def test_kg_import_hints_on_zero_relations(tmp_path: Path) -> None:
    """Relations come only from strict `doc_id#§N.ITEM` cross-references;
    an import that extracts entities but zero relations must say so instead
    of looking like a silent failure."""
    import shutil

    from cataforge.domain.kg._dispatch import invalidate_cache

    invalidate_cache()
    project = tmp_path / "proj"
    shutil.copytree(FIXTURE_ROOT / "waterfall", project)
    # Only the PRD: its F/AC definitions carry no xrefs, so relations == 0.
    result = CliRunner().invoke(
        _cli(),
        [
            "kg",
            "import",
            "--project-root",
            str(project),
            "--backend",
            "memory",
            "--doc-type",
            "prd",
        ],
    )
    invalidate_cache()
    assert result.exit_code == 0, result.output
    assert "relations=0" in result.output
    assert "doc_id#§" in result.output, result.output


def test_kg_import_doc_only_honors_explicit_doc_type(tmp_path: Path) -> None:
    """An explicit --doc-type overrides the doc-only default no-op gate."""
    from cataforge.domain.kg._dispatch import invalidate_cache

    invalidate_cache()
    project = _doc_only_project(tmp_path)
    result = CliRunner().invoke(
        _cli(),
        [
            "kg",
            "import",
            "--project-root",
            str(project),
            "--backend",
            "memory",
            "--doc-type",
            "prd",
            "--json",
        ],
    )
    invalidate_cache()
    assert result.exit_code == 0, result.output
    assert "doc-only" not in result.output


def test_kg_import_memory_backend(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        _cli(),
        [
            "kg",
            "import",
            "--project-root",
            str(FIXTURE_ROOT / "waterfall"),
            "--backend",
            "memory",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    stats = json.loads(result.output)
    assert stats["parsed_docs"] == 3
    assert stats["extracted_entities"] == 9
    assert stats["extracted_relations"] == 4
    assert stats["entities_written"] == 9
    assert stats["relations_written"] == 4
    assert stats["verify_ok"] is True


def test_kg_import_dry_run_exits_zero(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        _cli(),
        [
            "kg",
            "import",
            "--project-root",
            str(FIXTURE_ROOT / "agile"),
            "--backend",
            "memory",
            "--dry-run",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    stats = json.loads(result.output)
    assert stats["dry_run"] is True
    assert stats["entities_written"] == 0
    assert stats["relations_written"] == 0


def test_kg_import_aborts_on_cross_doc_collision(tmp_path: Path) -> None:
    """A diverging same-id definition within the authoritative doc_type exits 3
    (content gate) with an actionable unify-the-markdown message — not a
    silent overwrite."""
    project = tmp_path / "proj"
    d = project / "docs" / "prd"
    d.mkdir(parents=True)
    for doc_id, body in (
        ("prd-a", "# PRD A\n\n## §2 AC\n\n### AC-001 用户可登录\n\n登录成功返回 200。\n"),
        ("prd-b", "# PRD B\n\n## §2 AC\n\n### AC-001 锁定可解除\n\n三次失败后锁定。\n"),
    ):
        (d / f"{doc_id}.md").write_text(f"---\ndoc_id: {doc_id}\n---\n{body}", encoding="utf-8")

    result = CliRunner().invoke(
        _cli(),
        [
            "kg",
            "import",
            "--project-root",
            str(project),
            "--backend",
            "memory",
            "--doc-type",
            "prd",
        ],
    )
    assert result.exit_code == 3, result.output
    assert "AC-001" in result.output
    assert "prd-a" in result.output and "prd-b" in result.output
    assert "kg import" in result.output


def test_kg_import_then_validate_oxigraph_backend(tmp_path: Path) -> None:
    db = tmp_path / "store"
    runner = CliRunner()

    init = runner.invoke(_cli(), ["kg", "init", "--db-path", str(db), "--backend", "oxigraph"])
    assert init.exit_code == 0, init.output

    imp = runner.invoke(
        _cli(),
        [
            "kg",
            "import",
            "--project-root",
            str(FIXTURE_ROOT / "waterfall"),
            "--db-path",
            str(db),
            "--backend",
            "oxigraph",
        ],
    )
    assert imp.exit_code == 0, imp.output

    val = runner.invoke(_cli(), ["kg", "validate", "--db-path", str(db), "--json"])
    assert val.exit_code == 0, val.output
    report = json.loads(val.output)
    assert report["ok"] is True
    assert report["violations"] == []


def test_kg_export_end_to_end_oxigraph(tmp_path: Path) -> None:
    db = tmp_path / "store"
    out = tmp_path / "exported"
    runner = CliRunner()

    init = runner.invoke(_cli(), ["kg", "init", "--db-path", str(db), "--backend", "oxigraph"])
    assert init.exit_code == 0, init.output

    imp = runner.invoke(
        _cli(),
        [
            "kg",
            "import",
            "--project-root",
            str(FIXTURE_ROOT / "waterfall"),
            "--db-path",
            str(db),
            "--backend",
            "oxigraph",
        ],
    )
    assert imp.exit_code == 0, imp.output

    exp = runner.invoke(
        _cli(),
        [
            "kg",
            "export",
            "--db-path",
            str(db),
            "--output-dir",
            str(out),
            "--json",
        ],
    )
    assert exp.exit_code == 0, exp.output
    payload = json.loads(exp.output)
    assert payload["rendered"] == 9
    assert payload["errors"] == []
    assert set(payload["files"].keys()) == {
        "prd/F-001.md",
        "prd/F-002.md",
        "prd/AC-001.md",
        "prd/AC-002.md",
        "arch/M-001.md",
        "arch/M-002.md",
        "arch/TS-001.md",
        "test-report/TC-001.md",
        "test-report/TC-002.md",
    }
