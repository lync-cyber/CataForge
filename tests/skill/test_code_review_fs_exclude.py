"""Generated/vendored file exclusion — single ignore source feeding both
the lint file walk (``iter_files``) and the probe ignore globs
(``probe_ignore_globs``). Minified third-party bundles must never reach
ESLint/Prettier (config-error false-positive FAILs) nor jscpd."""

from __future__ import annotations

from pathlib import Path

from cataforge.runtime.skill.builtins.code_review.engine import fs
from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext


def test_iter_files_excludes_minified_bundles(tmp_path: Path) -> None:
    (tmp_path / "app.js").write_text("const a = 1;\n", encoding="utf-8")
    (tmp_path / "vendor.min.js").write_text("x", encoding="utf-8")
    (tmp_path / "styles.min.css").write_text("a{}", encoding="utf-8")
    (tmp_path / "bundle.map").write_text("{}", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    found = {p.name for p in fs.iter_files(tmp_path)}
    assert "app.js" in found  # real source still walked
    assert "vendor.min.js" not in found
    assert "styles.min.css" not in found
    assert "bundle.map" not in found
    assert "package-lock.json" not in found


def test_probe_ignore_globs_render_file_globs() -> None:
    globs = fs.probe_ignore_globs()
    assert "**/*.min.js" in globs
    assert "**/*.map" in globs
    # existing dir globs preserved
    for excluded in fs.EXCLUDE_DIRS:
        assert f"**/{excluded}/**" in globs
    assert "**/*.d.ts" in globs


def test_project_ignore_file_honored(tmp_path: Path) -> None:
    rules_dir = tmp_path / ".cataforge" / "skills" / "code-review"
    rules_dir.mkdir(parents=True)
    (rules_dir / "ignore").write_text(
        "# project-specific vendored assets\nthird_party_*.js\n", encoding="utf-8"
    )
    (tmp_path / "third_party_widget.js").write_text("x", encoding="utf-8")
    (tmp_path / "own.js").write_text("const a = 1;\n", encoding="utf-8")

    extra = fs.load_project_ignore(tmp_path)
    assert "third_party_*.js" in extra

    found = {p.name for p in fs.iter_files(tmp_path, extra)}
    assert "own.js" in found
    assert "third_party_widget.js" not in found


def test_context_all_files_applies_project_ignore(tmp_path: Path) -> None:
    rules_dir = tmp_path / ".cataforge" / "skills" / "code-review"
    rules_dir.mkdir(parents=True)
    (rules_dir / "ignore").write_text("legacy/**\n", encoding="utf-8")
    (tmp_path / "legacy").mkdir()
    (tmp_path / "legacy" / "old.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "new.py").write_text("y = 2\n", encoding="utf-8")

    ctx = CheckContext(target=tmp_path, project_root=tmp_path, mode="scan")
    names = {p.name for p in ctx.all_files()}
    assert "new.py" in names
    assert "old.py" not in names


def test_probe_ignore_globs_merges_project_ignore(tmp_path: Path) -> None:
    rules_dir = tmp_path / ".cataforge" / "skills" / "code-review"
    rules_dir.mkdir(parents=True)
    (rules_dir / "ignore").write_text("gen_*.py\n", encoding="utf-8")
    globs = fs.probe_ignore_globs(fs.load_project_ignore(tmp_path))
    assert "**/*.min.js" in globs
    assert "**/gen_*.py" in globs
