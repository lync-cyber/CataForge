"""`cataforge context` finalize / reconcile error paths route through CataforgeGroup.

Both commands previously called ``raise SystemExit(N)``, which bypasses the
``CataforgeGroup.invoke`` handler — so no unified ``Error:`` banner was rendered
and finalize collided with Click's usage exit code 2. They now raise a
``CataforgeError`` carrying an explicit exit code, which the group renders.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

import cataforge.application.context.write as write_app
from cataforge.interface.cli.context_cmd import (
    context_finalize,
    context_ingest,
    context_reconcile,
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
