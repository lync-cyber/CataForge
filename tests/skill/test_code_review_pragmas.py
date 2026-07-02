"""Unified exemption pragma: grammar, reason policy, consumer behavior."""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.checks import wiring
from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext
from cataforge.runtime.skill.builtins.code_review.engine.pragmas import (
    file_allowance,
    parse_allowances,
)


def test_parse_allowances_grammar_variants() -> None:
    text = (
        '// cataforge: allow(ui_fidelity, reason="dynamic theme tokens")\n'
        "# cataforge: allow(code_review.wiring_empty_handler)\n"
        '/* cataforge: allow( some-check , reason="spaced" ) */\n'
    )
    allowances = parse_allowances(text)
    assert [(a.check, a.reason, a.line) for a in allowances] == [
        ("ui_fidelity", "dynamic theme tokens", 1),
        ("code_review.wiring_empty_handler", "", 2),
        ("some-check", "spaced", 3),
    ]


def test_file_allowance_matches_full_id_and_specifier() -> None:
    by_specifier = '// cataforge: allow(ui_fidelity, reason="x")\n'
    by_full_id = '// cataforge: allow(code_review.ui_fidelity, reason="x")\n'
    assert file_allowance(by_specifier, "code_review.ui_fidelity") is not None
    assert file_allowance(by_full_id, "code_review.ui_fidelity") is not None
    assert file_allowance(by_specifier, "code_review.wiring_empty_handler") is None


def _write_tsx(tmp_path: Path, header: str) -> Path:
    src = tmp_path / "App.tsx"
    src.write_text(
        header + "export const App = () => <button onClick={() => {}}>go</button>;\n",
        encoding="utf-8",
    )
    return src


def test_wiring_allowance_with_reason_skips_file(tmp_path: Path) -> None:
    _write_tsx(tmp_path, '// cataforge: allow(wiring_empty_handler, reason="M2 backlog B-12")\n')
    ctx = CheckContext(target=tmp_path, project_root=None, mode="review")
    assert wiring.run(ctx) == []


def test_wiring_allowance_without_reason_warns_once(tmp_path: Path) -> None:
    _write_tsx(tmp_path, "// cataforge: allow(wiring_empty_handler)\n")
    ctx = CheckContext(target=tmp_path, project_root=None, mode="review")
    findings = wiring.run(ctx)
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert "缺 reason" in findings[0].detail


def test_wiring_legacy_placeholder_pragma_no_longer_recognized(tmp_path: Path) -> None:
    _write_tsx(tmp_path, "// cataforge: wiring-placeholder\n")
    ctx = CheckContext(target=tmp_path, project_root=None, mode="review")
    findings = wiring.run(ctx)
    assert findings, "legacy pragma must not suppress the scan anymore"
    assert all("onClick" in f.detail for f in findings)
