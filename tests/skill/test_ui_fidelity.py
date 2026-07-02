"""UI fidelity static checks (code-review Layer 1).

Catches the three mechanically-detectable UI defects that pass a green
test suite while rendering broken: dead design tokens (declared custom
property with zero ``var()`` consumers), unloaded fonts (referenced
``font-family`` with no loader), and ghost classes (markup class with no
CSS definition). Cross-file set-difference, resolved over the whole
corpus so a consumer in another file is not a false positive.
"""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.checks import ui_fidelity as uf


def _codes(findings: list[uf.Finding]) -> set[str]:
    return {f.code for f in findings}


def test_dead_token_flagged_when_no_consumer() -> None:
    files = {"tokens.css": "--text-display: 28px;\n--color-brand: #f00;\n"}
    findings = uf.analyze(files, files)
    dead = [f for f in findings if f.code == "dead_token"]
    assert {"--text-display", "--color-brand"} <= {d.token for d in dead}
    assert all(f.severity == "fail" for f in dead)


def test_token_with_var_consumer_is_clean() -> None:
    files = {
        "tokens.css": "--text-display: 28px;\n",
        "Heading.tsx": 'const s = { fontSize: "var(--text-display)" };\n',
    }
    assert "dead_token" not in _codes(uf.analyze(files, files))


def test_unloaded_font_warns() -> None:
    files = {"theme.css": 'body { font-family: "Inter", sans-serif; }\n'}
    findings = uf.analyze(files, files)
    fonts = [f for f in findings if f.code == "unloaded_font"]
    assert fonts and fonts[0].severity == "warn"
    assert "inter" in fonts[0].detail.lower()


def test_generic_family_never_flagged() -> None:
    files = {"theme.css": "body { font-family: sans-serif; }\n"}
    assert "unloaded_font" not in _codes(uf.analyze(files, files))


def test_font_loaded_via_fontsource_is_clean() -> None:
    files = {
        "theme.css": 'body { font-family: "Noto Sans SC", sans-serif; }\n',
        "main.ts": "import '@fontsource/noto-sans-sc';\n",
    }
    assert "unloaded_font" not in _codes(uf.analyze(files, files))


def test_font_loaded_via_font_face_is_clean() -> None:
    files = {
        "theme.css": (
            '@font-face { font-family: "Inter"; src: url(/inter.woff2); }\n'
            'body { font-family: "Inter", sans-serif; }\n'
        ),
    }
    assert "unloaded_font" not in _codes(uf.analyze(files, files))


def test_ghost_class_warns() -> None:
    files = {
        "NavSidebar.tsx": '<div className="nav-item brand-subtle">x</div>\n',
        "app.css": ".sidebar { color: red; }\n",
    }
    findings = uf.analyze(files, files)
    ghosts = [f for f in findings if f.code == "ghost_class"]
    assert {"nav-item", "brand-subtle"} <= {g.detail for g in ghosts}
    assert all(g.severity == "warn" for g in ghosts)


def test_defined_class_is_clean() -> None:
    files = {
        "NavSidebar.tsx": '<div className="nav-item">x</div>\n',
        "app.css": ".nav-item { color: red; }\n",
    }
    assert "ghost_class" not in _codes(uf.analyze(files, files))


def test_ghost_class_suppressed_under_utility_framework() -> None:
    files = {
        "NavSidebar.tsx": '<div className="flex gap-2 nav-item">x</div>\n',
        "app.css": "@tailwind base;\n@tailwind utilities;\n",
    }
    assert "ghost_class" not in _codes(uf.analyze(files, files))


def test_allow_pragma_with_reason_opts_file_out() -> None:
    target = {
        "tokens.css": '/* cataforge: allow(ui_fidelity, reason="dynamic tokens") */\n'
        "--text-x: 1px;\n"
    }
    findings = uf.analyze(target, target)
    assert findings == []


def test_allow_pragma_without_reason_suppresses_but_warns() -> None:
    target = {"tokens.css": "/* cataforge: allow(ui_fidelity) */\n--text-x: 1px;\n"}
    findings = uf.analyze(target, target)
    assert "dead_token" not in _codes(findings)
    warns = [f for f in findings if f.code == "allow_missing_reason"]
    assert warns and all(f.severity == "warn" for f in warns)


def test_legacy_pragma_string_no_longer_recognized() -> None:
    target = {"tokens.css": "/* cataforge-allow-ui-fidelity */\n--text-x: 1px;\n"}
    assert "dead_token" in _codes(uf.analyze(target, target))


def test_class_def_not_harvested_from_js_member_access() -> None:
    # `obj.nav` in TS is a property access, not a CSS class definition — it
    # must not satisfy a ghost-class reference.
    files = {
        "View.tsx": '<div className="nav">x</div>\n',
        "logic.ts": "const x = obj.nav.value;\n",
    }
    assert "nav" in {f.detail for f in uf.analyze(files, files) if f.code == "ghost_class"}


def test_consumer_resolved_across_corpus_not_just_target() -> None:
    # Per-task review of tokens.css: the only declared token is consumed in a
    # file outside the target set, so it must not be flagged.
    target = {"tokens.css": "--text-x: 1px;\n"}
    corpus = {**target, "page.tsx": "style={{ width: 'var(--text-x)' }}\n"}
    assert "dead_token" not in _codes(uf.analyze(target, corpus))


def test_scan_ui_fidelity_on_disk(tmp_path: Path) -> None:
    (tmp_path / "tokens.css").write_text("--dead-token: 9px;\n", encoding="utf-8")
    findings = uf.scan_ui_fidelity(tmp_path, tmp_path)
    assert "--dead-token" in {f.token for f in findings if f.code == "dead_token"}
