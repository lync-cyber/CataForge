"""Probe/linter launcher resolution for the code-review scan.

Probes and linters are declared by bare argv[0] (``npx``, ``vulture``,
``eslint``). On Windows those resolve to ``.CMD`` / ``.BAT`` shims, which
``subprocess`` (CreateProcess, appends only ``.exe``) cannot launch by bare
name — it raises ``FileNotFoundError`` and the probe is silently skipped as
"未安装". Resolving argv[0] through ``shutil.which`` (PATHEXT-aware) yields a
launchable absolute path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.runtime.skill.builtins.code_review import code_lint


def test_resolved_rewrites_argv0_to_which_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        code_lint.shutil,
        "which",
        lambda name: r"C:\Program Files\nodejs\npx.CMD" if name == "npx" else None,
    )
    assert code_lint._resolved(["npx", "jscpd", "--silent", "src"]) == [
        r"C:\Program Files\nodejs\npx.CMD",
        "jscpd",
        "--silent",
        "src",
    ]


def test_resolved_leaves_missing_tool_bare(monkeypatch: pytest.MonkeyPatch) -> None:
    # A genuinely absent tool stays bare so the existing FileNotFoundError
    # -> "未安装，跳过" skip path still fires.
    monkeypatch.setattr(code_lint.shutil, "which", lambda name: None)
    assert code_lint._resolved(["radon", "cc", "src"]) == ["radon", "cc", "src"]


def test_run_probe_launches_resolved_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(code_lint.shutil, "which", lambda name: f"/resolved/{name}")

    launched: list[list[str]] = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(argv: list[str], **_: object) -> _Result:
        launched.append(list(argv))
        return _Result()

    monkeypatch.setattr(code_lint, "run_proc", _fake_run)

    scanner = code_lint.CodeScanner(str(tmp_path), focus=["dead-code"])
    probe = code_lint.SCAN_PROBES["dead-code"][0]  # vulture
    scanner.run_probe(probe, {".py"})

    # Both the detect probe and the build_cmd run go through the resolved path.
    assert launched, "run_probe never launched the probe"
    assert all(call[0] == "/resolved/vulture" for call in launched)


def test_iter_files_prunes_excluded_dirs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "b.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "c.py").write_text("z = 3\n", encoding="utf-8")

    found = {p.name for p in code_lint._iter_files(tmp_path)}
    assert "a.py" in found
    assert "b.py" not in found  # node_modules pruned
    assert "c.py" not in found  # __pycache__ pruned
