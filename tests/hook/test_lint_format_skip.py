"""lint_format must never auto-format framework assets under .cataforge/."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# ruff format rewrites this to "x = 1\n"; an unchanged file proves the hook
# never reached the formatter.
MESSY = "x=1\n"
FORMATTED = "x = 1\n"


def _run(project_root: Path, file_path: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project_root), "PYTHONUTF8": "1"}
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(file_path)}}
    return subprocess.run(
        [sys.executable, "-m", "cataforge.runtime.hook.scripts.lint_format"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        cwd=str(project_root),
        env=env,
        timeout=30,
    )


def _bootstrap(tmp_path: Path) -> Path:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        json.dumps({"version": "0.1.0", "runtime": {"platform": "claude-code"}}),
        encoding="utf-8",
    )
    return tmp_path


def test_lint_format_skips_cataforge_py(tmp_path: Path) -> None:
    project = _bootstrap(tmp_path)
    target = project / ".cataforge" / "hooks" / "custom" / "messy.py"
    target.parent.mkdir(parents=True)
    target.write_text(MESSY, encoding="utf-8")

    proc = _run(project, target)
    assert proc.returncode == 0, proc.stderr.decode()
    assert target.read_text(encoding="utf-8") == MESSY


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
def test_lint_format_formats_non_cataforge_py(tmp_path: Path) -> None:
    project = _bootstrap(tmp_path)
    target = project / "src" / "messy.py"
    target.parent.mkdir(parents=True)
    target.write_text(MESSY, encoding="utf-8")

    proc = _run(project, target)
    assert proc.returncode == 0, proc.stderr.decode()
    assert target.read_text(encoding="utf-8") == FORMATTED
