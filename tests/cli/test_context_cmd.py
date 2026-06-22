"""`cataforge context` finalize / reconcile error paths route through CataforgeGroup.

Both commands previously called ``raise SystemExit(N)``, which bypasses the
``CataforgeGroup.invoke`` handler — so no unified ``Error:`` banner was rendered
and finalize collided with Click's usage exit code 2. They now raise a
``CataforgeError`` carrying an explicit exit code, which the group renders.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import cataforge.application.context.write as write_app
from cataforge.interface.cli.context_cmd import (
    context_finalize,
    context_ingest,
    context_reconcile,
    context_write,
    context_write_narrative,
)
from cataforge.interface.cli.main import cli
from tests.cli.conftest import invoke_under_group


def test_finalize_export_error_renders_banner_exit_1(monkeypatch) -> None:
    fake = SimpleNamespace(
        file_records=[],
        errors=[("E-001", "render failed")],
    )
    monkeypatch.setattr(write_app, "finalize", lambda *a, **k: fake)

    result = invoke_under_group(context_finalize, ["--project-root", "."])

    assert result.exit_code == 1, result.output
    assert "Error:" in result.output


def test_reconcile_drift_renders_banner_exit_3(monkeypatch) -> None:
    report = SimpleNamespace(ok=False, overall_divergence_count=2)
    monkeypatch.setattr(write_app, "reconcile_check", lambda *a, **k: report)

    result = invoke_under_group(context_reconcile, ["--project-root", "."])

    assert result.exit_code == 3, result.output
    assert "Error:" in result.output


def test_reconcile_missing_store_renders_init_hint_exit_1(monkeypatch) -> None:
    """A project that never ran ``kg init`` must get a clean ``Error:`` + hint,
    not an uncaught ``KGStoreNotInitializedError`` traceback."""
    from cataforge.domain.kg import KGStoreNotInitializedError

    def _boom(*_a, **_k):
        raise KGStoreNotInitializedError("store not initialised at .cataforge/kg/store")

    monkeypatch.setattr(write_app, "reconcile_check", _boom)

    result = invoke_under_group(context_reconcile, ["--project-root", "."])

    assert result.exit_code == 1, result.output
    assert "Error:" in result.output
    assert "kg init" in result.output


def test_ingest_missing_store_renders_init_hint_exit_1(monkeypatch) -> None:
    from cataforge.domain.kg import KGStoreNotInitializedError

    def _boom(*_a, **_k):
        raise KGStoreNotInitializedError("store not initialised at .cataforge/kg/store")

    monkeypatch.setattr(write_app, "ingest", _boom)

    result = invoke_under_group(context_ingest, ["--project-root", "."])

    assert result.exit_code == 1, result.output
    assert "Error:" in result.output
    assert "kg init" in result.output


def test_global_project_dir_reaches_reconcile(tmp_path: Path, monkeypatch) -> None:
    """`--project-dir` must re-root a defaulted `--project-root`. Regression:
    the context commands carried their own `--project-root` (default cwd) and
    ignored the global flag, so a sandbox run reconciled the host graph."""
    target = tmp_path / "target"
    (target / ".cataforge").mkdir(parents=True)
    captured: dict[str, str] = {}

    def _fake(project_root):
        captured["root"] = project_root
        return SimpleNamespace(ok=True, overall_divergence_count=0)

    monkeypatch.setattr(write_app, "reconcile_check", _fake)
    monkeypatch.chdir(tmp_path)  # cwd != target

    result = CliRunner().invoke(cli, ["--project-dir", str(target), "context", "reconcile"])

    assert result.exit_code == 0, result.output
    assert Path(captured["root"]) == target.resolve()


def test_explicit_project_root_wins_over_global(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "target"
    (target / ".cataforge").mkdir(parents=True)
    explicit = tmp_path / "explicit"
    captured: dict[str, str] = {}

    def _fake(project_root):
        captured["root"] = project_root
        return SimpleNamespace(ok=True, overall_divergence_count=0)

    monkeypatch.setattr(write_app, "reconcile_check", _fake)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli,
        ["--project-dir", str(target), "context", "reconcile", "--project-root", str(explicit)],
    )

    assert result.exit_code == 0, result.output
    assert captured["root"] == str(explicit)


# ---- doc-only strategy routing ----------------------------------------------


@pytest.fixture
def _clear_dispatch_cache():
    from cataforge.domain.kg._dispatch import invalidate_cache

    invalidate_cache()
    yield
    invalidate_cache()


def _doc_only_project(tmp_path: Path) -> Path:
    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"mode": "markdown"}}), encoding="utf-8"
    )
    doc = proj / "docs" / "prd" / "prd.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("---\nid: prd\ndoc_type: prd\n---\n# PRD\n", encoding="utf-8")
    return proj


def test_finalize_doc_only_reports_indexed_docs(tmp_path: Path, _clear_dispatch_cache) -> None:
    proj = _doc_only_project(tmp_path)

    result = invoke_under_group(context_finalize, ["--project-root", str(proj)])

    assert result.exit_code == 0, result.output
    assert "indexed 1 doc(s)" in result.output
    assert (proj / "docs" / ".doc-index.json").is_file()


def test_ingest_doc_only_reports_indexed_docs(tmp_path: Path, _clear_dispatch_cache) -> None:
    proj = _doc_only_project(tmp_path)

    result = invoke_under_group(context_ingest, ["--project-root", str(proj)])

    assert result.exit_code == 0, result.output
    assert "indexed 1 doc(s)" in result.output
    assert (proj / "docs" / ".doc-index.json").is_file()


def test_reconcile_doc_only_clean_index_exits_0(tmp_path: Path, _clear_dispatch_cache) -> None:
    proj = _doc_only_project(tmp_path)
    invoke_under_group(context_finalize, ["--project-root", str(proj)])

    result = invoke_under_group(context_reconcile, ["--project-root", str(proj)])

    assert result.exit_code == 0, result.output
    assert "reconcile OK" in result.output


def test_reconcile_doc_only_orphan_exits_3(tmp_path: Path, _clear_dispatch_cache) -> None:
    proj = _doc_only_project(tmp_path)
    invoke_under_group(context_finalize, ["--project-root", str(proj)])
    orphan = proj / "docs" / "research" / "orphan.md"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("# no front matter\n", encoding="utf-8")

    result = invoke_under_group(context_reconcile, ["--project-root", str(proj)])

    assert result.exit_code == 3, result.output
    assert "Error:" in result.output


def test_context_reconcile_json_clean_index(tmp_path: Path, _clear_dispatch_cache) -> None:
    # --json surfaces the full report and exits 0 on a clean docs index.
    proj = _doc_only_project(tmp_path)
    invoke_under_group(context_finalize, ["--project-root", str(proj)])

    result = invoke_under_group(context_reconcile, ["--project-root", str(proj), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["overall_divergence_count"] == 0


def test_context_reconcile_json_drift_exit_3(tmp_path: Path, _clear_dispatch_cache) -> None:
    # On drift, --json still emits the report but exits 3 (gate semantics intact).
    proj = _doc_only_project(tmp_path)
    invoke_under_group(context_finalize, ["--project-root", str(proj)])
    orphan = proj / "docs" / "research" / "orphan.md"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("# no front matter\n", encoding="utf-8")

    result = invoke_under_group(context_reconcile, ["--project-root", str(proj), "--json"])

    assert result.exit_code == 3, result.output
    # The JSON body precedes the error banner.
    first_line = result.output.splitlines()[0]
    assert json.loads(first_line)["ok"] is False


def test_write_doc_only_rejected_without_kg_init_hint(
    tmp_path: Path, _clear_dispatch_cache
) -> None:
    proj = _doc_only_project(tmp_path)

    result = invoke_under_group(
        context_write,
        [
            "--entity-id",
            "F-001",
            "--class",
            "Feature",
            "--title",
            "登录",
            "--project-root",
            str(proj),
        ],
    )

    assert result.exit_code == 1, result.output
    assert "Error:" in result.output
    assert "context.mode" in result.output
    assert "kg init" not in result.output


def test_write_narrative_doc_only_rejected_without_kg_init_hint(
    tmp_path: Path, _clear_dispatch_cache
) -> None:
    proj = _doc_only_project(tmp_path)

    result = invoke_under_group(
        context_write_narrative,
        [
            "--doc-id",
            "prd",
            "--anchor",
            "§1 概览",
            "--narrative",
            "文本",
            "--project-root",
            str(proj),
        ],
    )

    assert result.exit_code == 1, result.output
    assert "Error:" in result.output
    assert "context.mode" in result.output
    assert "kg init" not in result.output


def _project_root_param(command):
    for param in command.params:
        if param.name == "project_root":
            return param
    return None


def test_context_commands_project_root_consistent() -> None:
    """Every context command's ``--project-root`` shares one type + default.

    The facade previously mixed ``default=None`` (read/index/validate) with
    ``default="."`` (the authoring verbs), so callers couldn't reason about a
    single contract. They now agree, and all route the global ``--project-dir``.
    """
    from cataforge.interface.cli.context_cmd import context_group

    rooted = {
        name: _project_root_param(cmd)
        for name, cmd in context_group.commands.items()
        if _project_root_param(cmd) is not None
    }
    assert rooted, "expected context commands to carry --project-root"

    defaults = {name: p.default for name, p in rooted.items()}
    assert set(defaults.values()) == {None}, f"inconsistent defaults: {defaults}"

    types = {name: type(p.type).__name__ for name, p in rooted.items()}
    assert len(set(types.values())) == 1, f"inconsistent types: {types}"


def test_context_status_honours_global_project_dir(tmp_path: Path, _clear_dispatch_cache) -> None:
    """A defaulted ``--project-root`` re-roots under the global ``--project-dir``."""
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"mode": "markdown"}}), encoding="utf-8"
    )

    result = CliRunner().invoke(cli, ["--project-dir", str(tmp_path), "context", "status"])
    assert result.exit_code == 0, result.output
    assert "mode: markdown" in result.output
