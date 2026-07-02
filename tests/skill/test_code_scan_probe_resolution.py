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

from cataforge.runtime.skill.builtins.code_review.checks import probes
from cataforge.runtime.skill.builtins.code_review.engine import context, fs
from cataforge.runtime.skill.builtins.code_review.engine.context import CheckContext


def _probe(name: str) -> probes.Probe:
    return next(p for p in probes.PROBES if p.name == name)


def test_resolved_rewrites_argv0_to_which_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fs.shutil,
        "which",
        lambda name: r"C:\Program Files\nodejs\npx.CMD" if name == "npx" else None,
    )
    assert fs.resolved(["npx", "jscpd", "--silent", "src"]) == [
        r"C:\Program Files\nodejs\npx.CMD",
        "jscpd",
        "--silent",
        "src",
    ]


def test_resolved_leaves_missing_tool_bare(monkeypatch: pytest.MonkeyPatch) -> None:
    # A genuinely absent tool stays bare so the existing FileNotFoundError
    # -> "未安装，跳过" skip path still fires.
    monkeypatch.setattr(fs.shutil, "which", lambda name: None)
    assert fs.resolved(["radon", "cc", "src"]) == ["radon", "cc", "src"]


def test_probe_runner_launches_resolved_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(fs.shutil, "which", lambda name: f"/resolved/{name}")

    launched: list[list[str]] = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(argv: list[str], **_: object) -> _Result:
        launched.append(list(argv))
        return _Result()

    monkeypatch.setattr(context, "run_proc", _fake_run)
    monkeypatch.setattr(probes, "run_proc", _fake_run)

    ctx = CheckContext(target=tmp_path, project_root=tmp_path, mode="scan")
    vulture = _probe("vulture")
    probes._make_runner(vulture)(ctx)

    # Both the detect probe and the build_cmd run go through the resolved path.
    assert launched, "probe runner never launched the probe"
    assert all(call[0] == "/resolved/vulture" for call in launched)


def test_jscpd_build_cmd_ignores_excluded_dirs() -> None:
    # jscpd walks the target tree itself, so EXCLUDE_DIRS pruning in
    # iter_files never reaches it — without an explicit --ignore a
    # workspace package's node_modules blows the probe timeout.
    cmd = _probe("jscpd").build_cmd(Path("pkg"))
    assert "--ignore" in cmd
    globs = cmd[cmd.index("--ignore") + 1]
    for excluded in fs.EXCLUDE_DIRS:
        assert f"**/{excluded}/**" in globs
    assert "**/*.d.ts" in globs


def test_exclude_dirs_cover_svelte_kit_build_output() -> None:
    assert ".svelte-kit" in fs.EXCLUDE_DIRS


def test_dead_code_probes_cover_svelte_via_knip() -> None:
    knip = _probe("knip")
    assert knip.category == "dead-code"
    assert {".ts", ".svelte"} <= knip.extensions


def test_complexity_probes_cover_typescript() -> None:
    ts_probes = [p for p in probes.PROBES if p.category == "complexity" and ".ts" in p.extensions]
    assert ts_probes, "complexity category has no TypeScript-capable probe"


def test_iter_files_prunes_excluded_dirs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "b.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "c.py").write_text("z = 3\n", encoding="utf-8")

    found = {p.name for p in fs.iter_files(tmp_path)}
    assert "a.py" in found
    assert "b.py" not in found  # node_modules pruned
    assert "c.py" not in found  # __pycache__ pruned
