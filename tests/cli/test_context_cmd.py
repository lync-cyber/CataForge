"""`cataforge context` finalize / reconcile error paths route through CataforgeGroup.

Both commands previously called ``raise SystemExit(N)``, which bypasses the
``CataforgeGroup.invoke`` handler — so no unified ``Error:`` banner was rendered
and finalize collided with Click's usage exit code 2. They now raise a
``CataforgeError`` carrying an explicit exit code, which the group renders.
"""

from __future__ import annotations

from types import SimpleNamespace

import cataforge.application.context.write as write_app
from cataforge.interface.cli.context_cmd import context_finalize, context_reconcile
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
