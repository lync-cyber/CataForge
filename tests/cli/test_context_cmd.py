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
    context_delete,
    context_finalize,
    context_ingest,
    context_reconcile,
    context_update,
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


# ---- update / delete facade (M1 / M2) ---------------------------------------


def test_update_doc_only_rejected_without_kg_init_hint(
    tmp_path: Path, _clear_dispatch_cache
) -> None:
    proj = _doc_only_project(tmp_path)

    result = invoke_under_group(
        context_update,
        ["F-001", "--title", "x", "--project-root", str(proj)],
    )

    assert result.exit_code == 1, result.output
    assert "Error:" in result.output
    assert "context.mode" in result.output
    assert "kg init" not in result.output


def test_delete_doc_only_rejected_without_kg_init_hint(
    tmp_path: Path, _clear_dispatch_cache
) -> None:
    proj = _doc_only_project(tmp_path)

    result = invoke_under_group(
        context_delete,
        ["F-001", "--yes", "--project-root", str(proj)],
    )

    assert result.exit_code == 1, result.output
    assert "Error:" in result.output
    assert "context.mode" in result.output
    assert "kg init" not in result.output


def test_update_requires_at_least_one_field(tmp_path: Path, _clear_dispatch_cache) -> None:
    proj = _doc_only_project(tmp_path)

    result = invoke_under_group(context_update, ["F-001", "--project-root", str(proj)])

    assert result.exit_code != 0, result.output
    assert "at least one" in result.output


def _graph_project(tmp_path: Path) -> Path:
    """A graph-mode project with an initialized store, built via `kg init` only."""
    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    (proj / "docs").mkdir()
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"mode": "graph", "kg_active_doc_types": ["prd"]}}),
        encoding="utf-8",
    )
    db = proj / ".cataforge" / "kg" / "store"
    init = CliRunner().invoke(cli, ["kg", "init", "--db-path", str(db)])
    assert init.exit_code == 0, init.output
    return proj


def test_context_facade_covers_lifecycle_without_kg_business_verbs(
    tmp_path: Path, _clear_dispatch_cache
) -> None:
    """U3 regression: write → finalize → reconcile → update → delete all run
    through `context *`; only `kg init` (store mechanic) is needed, never a kg
    *business* verb."""
    proj = _graph_project(tmp_path)
    runner = CliRunner()
    root = ["--project-root", str(proj)]

    written = runner.invoke(
        cli,
        [
            "context",
            "write",
            "--entity-id",
            "F-001",
            "--class",
            "Feature",
            "--title",
            "登录",
            *root,
        ],
    )
    assert written.exit_code == 0, written.output

    finalized = runner.invoke(cli, ["context", "finalize", *root])
    assert finalized.exit_code == 0, finalized.output

    reconciled = runner.invoke(cli, ["context", "reconcile", *root])
    assert reconciled.exit_code == 0, reconciled.output

    updated = runner.invoke(cli, ["context", "update", "F-001", "--title", "登录v2", *root])
    assert updated.exit_code == 0, updated.output
    assert "updated F-001" in updated.output

    deleted = runner.invoke(cli, ["context", "delete", "F-001", "--yes", *root])
    assert deleted.exit_code == 0, deleted.output
    assert "deleted F-001" in deleted.output


def test_context_delete_json_round_trip(tmp_path: Path, _clear_dispatch_cache) -> None:
    proj = _graph_project(tmp_path)
    runner = CliRunner()
    root = ["--project-root", str(proj)]
    assert (
        runner.invoke(
            cli,
            [
                "context",
                "write",
                "--entity-id",
                "F-001",
                "--class",
                "Feature",
                "--title",
                "登录",
                *root,
            ],
        ).exit_code
        == 0
    )

    result = runner.invoke(cli, ["context", "delete", "F-001", "--json", *root])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["entity_id"] == "F-001"
    assert payload["quads_removed"] > 0


def _write_feature_with_incoming_edge(runner: CliRunner, root: list[str]) -> None:
    """Author F-001 plus an M-001 that ``implements`` it (an edge into F-001)."""
    runner.invoke(
        cli,
        [
            "context",
            "write",
            "--entity-id",
            "F-001",
            "--class",
            "Feature",
            "--title",
            "登录",
            *root,
        ],
    )
    added = runner.invoke(
        cli,
        [
            "context",
            "write",
            "--entity-id",
            "M-001",
            "--class",
            "Module",
            "--title",
            "Auth",
            "--relation",
            "cf:implements=F-001",
            *root,
        ],
    )
    assert added.exit_code == 0, added.output


def test_context_delete_rejects_incoming_edges_without_cascade(
    tmp_path: Path, _clear_dispatch_cache
) -> None:
    proj = _graph_project(tmp_path)
    runner = CliRunner()
    root = ["--project-root", str(proj)]
    _write_feature_with_incoming_edge(runner, root)

    result = runner.invoke(cli, ["context", "delete", "F-001", "--yes", *root])

    assert result.exit_code != 0, result.output
    assert "incoming edge" in result.output  # txn rejection透传到 facade
    assert "--cascade" in result.output  # facade 包装的 cascade hint


def test_context_delete_cascade_removes_incoming_edges(
    tmp_path: Path, _clear_dispatch_cache
) -> None:
    proj = _graph_project(tmp_path)
    runner = CliRunner()
    root = ["--project-root", str(proj)]
    _write_feature_with_incoming_edge(runner, root)

    result = runner.invoke(cli, ["context", "delete", "F-001", "--yes", "--cascade", *root])
    assert result.exit_code == 0, result.output
    assert "cascade" in result.output

    # F-001 is gone — a second facade delete now reports it absent.
    again = runner.invoke(cli, ["context", "delete", "F-001", "--yes", *root])
    assert again.exit_code != 0
    assert "not found" in again.output.lower()


def test_context_status_honours_global_project_dir(tmp_path: Path, _clear_dispatch_cache) -> None:
    """A defaulted ``--project-root`` re-roots under the global ``--project-dir``."""
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps({"context": {"mode": "markdown"}}), encoding="utf-8"
    )

    result = CliRunner().invoke(cli, ["--project-dir", str(tmp_path), "context", "status"])
    assert result.exit_code == 0, result.output
    assert "mode: markdown" in result.output
