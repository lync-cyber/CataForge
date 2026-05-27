"""Tests for cataforge.cli.diagnostics — pattern registry sanity."""

from __future__ import annotations

from cataforge.cli.diagnostics import (
    DOCTOR_PATTERNS,
    NGINX_UPSTREAM_MISSING,
    PENPOT_PATTERNS,
    PNPM_IGNORED_BUILDS,
    PORT_IN_USE,
    UPGRADE_PATTERNS,
)
from cataforge.cli.ui import UI, DiagPattern


def _ui_with_buffers():
    import io
    out = io.StringIO()
    err = io.StringIO()
    return UI(color=False, unicode=True, stdout=out, stderr=err), out, err


def test_pnpm_ignored_builds_pattern_matches() -> None:
    ui, out, _ = _ui_with_buffers()
    log = "Lockfile up to date\n ERR_PNPM_IGNORED_BUILDS Ignored build scripts"
    matched = ui.diagnose(log, [PNPM_IGNORED_BUILDS])
    assert matched == [PNPM_IGNORED_BUILDS]
    assert "pnpm" in out.getvalue()


def test_nginx_upstream_pattern_matches() -> None:
    ui, out, _ = _ui_with_buffers()
    log = 'nginx: [emerg] host not found in upstream "penpot-mcp"'
    matched = ui.diagnose(log, [NGINX_UPSTREAM_MISSING])
    assert matched == [NGINX_UPSTREAM_MISSING]
    assert "penpot-mcp" in out.getvalue() or "nginx" in out.getvalue()
    assert "cataforge penpot deploy" in out.getvalue()


def test_port_in_use_pattern_matches() -> None:
    ui, out, _ = _ui_with_buffers()
    matched = ui.diagnose("Error: listen EADDRINUSE :::4401", [PORT_IN_USE])
    assert matched == [PORT_IN_USE]
    assert "cataforge penpot stop" in out.getvalue()


def test_penpot_patterns_include_three_canonical_failures() -> None:
    assert PNPM_IGNORED_BUILDS in PENPOT_PATTERNS
    assert NGINX_UPSTREAM_MISSING in PENPOT_PATTERNS
    assert PORT_IN_USE in PENPOT_PATTERNS


def test_doctor_patterns_cover_missing_tools() -> None:
    needles = {
        p.needle if isinstance(p.needle, str) else p.needle.pattern
        for p in DOCTOR_PATTERNS
    }
    assert any("ruff" in n for n in needles)
    assert any("npx" in n for n in needles)
    assert any("docker" in n for n in needles)


def test_upgrade_patterns_are_registered() -> None:
    assert len(UPGRADE_PATTERNS) >= 1


def test_all_patterns_have_diagnosis_and_fix_action() -> None:
    """Sanity invariant: every entry must give the user something actionable."""
    all_patterns: list[DiagPattern] = (
        list(PENPOT_PATTERNS) + list(DOCTOR_PATTERNS) + list(UPGRADE_PATTERNS)
    )
    for p in all_patterns:
        assert p.diagnosis, f"missing diagnosis on {p}"
        assert p.fix_action, f"missing fix_action on {p}"
