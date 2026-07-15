"""code-review pipeline behavior: gating, focus semantics, renderers, CLI.

Hermetic: external tool availability is pre-seeded via ``tool_cache`` so
no linter/probe subprocess ever launches.
"""

from __future__ import annotations

import json
from pathlib import Path

from cataforge.runtime.skill.builtins.code_review import code_check
from cataforge.runtime.skill.builtins.code_review.engine.findings import (
    render_json,
    render_text,
)
from cataforge.runtime.skill.builtins.code_review.engine.pipeline import execute

_NO_TOOLS = {
    "ESLint": False,
    "Prettier": False,
    "Ruff Check": False,
    "Ruff Format": False,
    "dotnet format": False,
    "golangci-lint": False,
    "clippy": False,
    "jscpd": False,
    "pmd-cpd": False,
    "vulture": False,
    "ts-prune": False,
    "knip": False,
    "cargo-machete": False,
    "radon (cc)": False,
    "gocyclo": False,
    "eslint (complexity)": False,
    "lizard": False,
}


def _fixture(tmp_path: Path, *, dead_token: bool) -> Path:
    (tmp_path / "App.tsx").write_text(
        "export const App = () => <button onClick={() => {}}>go</button>;\n",
        encoding="utf-8",
    )
    css = ".used { color: var(--live); }\n:root { --live: #f00; }\n"
    if dead_token:
        css += ":root { --dead: 28px; }\n"
    (tmp_path / "tokens.css").write_text(css, encoding="utf-8")
    return tmp_path


def test_review_wiring_warn_does_not_gate(tmp_path: Path) -> None:
    target = _fixture(tmp_path, dead_token=False)
    result = execute("review", target, project_root=target, tool_cache=dict(_NO_TOOLS))
    assert result.exit_code == 0
    warns = [f for f in result.findings if f.check_id == "code_review.wiring_empty_handler"]
    assert [w.line for w in warns] == [1]


def test_eslint_skipped_with_warn_when_project_has_no_config(tmp_path: Path) -> None:
    """A resolvable ESLint binary on a project that never adopted ESLint
    (no config file at the root) is "not configured", not a lint failure."""
    target = _fixture(tmp_path, dead_token=False)
    tools = dict(_NO_TOOLS)
    tools["ESLint"] = True
    result = execute("review", target, project_root=target, tool_cache=tools)
    assert result.exit_code == 0
    eslint = [f for f in result.findings if f.check_id == "code_review.eslint"]
    assert eslint and all(f.severity == "warn" for f in eslint)
    assert "未发现配置" in eslint[0].detail


def test_eslint_config_markers_cover_flat_and_legacy(tmp_path: Path) -> None:
    from cataforge.runtime.skill.builtins.code_review.checks.external_tools import (
        _ESLINT_CONFIG_MARKERS,
    )

    assert not any((tmp_path / m).is_file() for m in _ESLINT_CONFIG_MARKERS)
    (tmp_path / "eslint.config.mjs").write_text("export default [];\n")
    assert any((tmp_path / m).is_file() for m in _ESLINT_CONFIG_MARKERS)
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / ".eslintrc.json").write_text("{}\n")
    assert any((legacy / m).is_file() for m in _ESLINT_CONFIG_MARKERS)


def test_review_dead_token_gates(tmp_path: Path) -> None:
    target = _fixture(tmp_path, dead_token=True)
    result = execute("review", target, project_root=target, tool_cache=dict(_NO_TOOLS))
    assert result.exit_code == 1
    fails = [f for f in result.findings if f.severity == "fail"]
    assert fails and all(f.check_id == "code_review.ui_fidelity" for f in fails)
    assert "--dead" in fails[0].detail


def test_review_focus_converges_checks(tmp_path: Path) -> None:
    target = _fixture(tmp_path, dead_token=True)
    result = execute(
        "review",
        target,
        focus=["integration-wiring"],
        project_root=target,
        tool_cache=dict(_NO_TOOLS),
    )
    assert result.checks_run == ["code_review.wiring_empty_handler"]
    assert result.exit_code == 0  # the dead token is outside the focused dimension


def test_scan_focus_never_disables_gating_checks(tmp_path: Path) -> None:
    target = _fixture(tmp_path, dead_token=True)
    result = execute(
        "scan",
        target,
        focus=["duplication"],
        project_root=target,
        tool_cache=dict(_NO_TOOLS),
    )
    assert "code_review.ui_fidelity" in result.checks_run
    assert "code_review.probe_vulture" not in result.checks_run  # dead-code filtered out
    assert result.exit_code == 1  # gating dead_token still fails the scan


def test_missing_probe_tool_is_info_not_gate(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    result = execute("scan", tmp_path, project_root=tmp_path, tool_cache=dict(_NO_TOOLS))
    assert result.exit_code == 0
    # A supplementary probe (radon/vulture/…) being absent is info, not warn:
    # the dimension it augments has a built-in floor, so it stays in the
    # truncatable info section rather than the prominent warn list.
    probe_missing = [f for f in result.findings if "probe '" in f.detail and "未安装" in f.detail]
    assert probe_missing and all(f.severity == "info" for f in probe_missing)


def test_missing_linter_tool_stays_warn_not_gate(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    result = execute("scan", tmp_path, project_root=tmp_path, tool_cache=dict(_NO_TOOLS))
    assert result.exit_code == 0
    # A missing primary linter (Ruff for .py here) means that language is not
    # linted at all — a real coverage gap worth a prominent warn (still non-gating).
    linter_missing = [
        f for f in result.findings if "未安装" in f.detail and "probe '" not in f.detail
    ]
    assert linter_missing and all(f.severity == "warn" for f in linter_missing)


def test_renderers_agree_on_result(tmp_path: Path) -> None:
    target = _fixture(tmp_path, dead_token=True)
    result = execute("review", target, project_root=target, tool_cache=dict(_NO_TOOLS))
    text = render_text(result)
    assert "RESULT: FAIL" in text
    payload = json.loads(render_json(result))
    assert payload["result"] == "FAIL"
    assert payload["summary"]["fail"] == len([f for f in result.findings if f.severity == "fail"])
    assert {f["check_id"] for f in payload["findings"]} == {f.check_id for f in result.findings}


def test_cli_run_invalid_focus_is_usage_error(tmp_path: Path) -> None:
    assert code_check.run("review", str(tmp_path), focus=["bogus"]) == 2


def test_cli_run_missing_target_is_usage_error(tmp_path: Path) -> None:
    assert code_check.run("review", str(tmp_path / "nope")) == 2


def test_cli_parser_rejects_unknown_flags(capsys: object) -> None:
    import pytest

    parser = code_check.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["review", "x", "--bogus"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        parser.parse_args([])
    assert exc.value.code == 2
