"""Self-test for ``scripts/checks/check_prompt_cli_drift.py``.

The guard prevents prompts from referencing phantom CLI verbs (a
``context write-section`` that the CLI never registered). Without these
tests a regex tweak could silently stop matching real violations.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "checks" / "check_prompt_cli_drift.py"


def _run_against(tmp_root: Path) -> subprocess.CompletedProcess[str]:
    """Run the guard with SCAN_GLOBS pointed at *tmp_root* (real verbs still
    introspected from the installed CLI)."""
    runner = (
        "import sys, pathlib;"
        f"sys.path.insert(0, {str(REPO_ROOT / 'scripts' / 'checks')!r});"
        "import importlib.util as iu;"
        f"spec = iu.spec_from_file_location('guard', {str(SCRIPT)!r});"
        "mod = iu.module_from_spec(spec); spec.loader.exec_module(mod);"
        f"mod.REPO_ROOT = pathlib.Path({str(tmp_root)!r});"
        f"mod.SCAN_GLOBS = [(pathlib.Path({str(tmp_root)!r}), '**/*.md')];"
        "sys.exit(mod.main())"
    )
    return subprocess.run(
        [sys.executable, "-c", runner], capture_output=True, text=True, encoding="utf-8"
    )


def _write(tmp_path: Path, body: str) -> None:
    (tmp_path / "SKILL.md").write_text(body, encoding="utf-8")


def test_passes_on_real_verbs(tmp_path: Path) -> None:
    _write(tmp_path, "用 `cataforge context finalize` 导出;`context read` 加载章节。\n")
    result = _run_against(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout


def test_flags_backtick_phantom_verb(tmp_path: Path) -> None:
    _write(tmp_path, "通过 `context write-section` 改章节。\n")
    result = _run_against(tmp_path)
    assert result.returncode == 1
    assert "write-section" in result.stderr


def test_flags_cataforge_prefixed_phantom_verb(tmp_path: Path) -> None:
    _write(tmp_path, "跑 cataforge context bogus-verb 试试。\n")
    result = _run_against(tmp_path)
    assert result.returncode == 1
    assert "bogus-verb" in result.stderr


def test_ignores_concept_prose(tmp_path: Path) -> None:
    """Bare 'context authoring' (no backtick, no cataforge) is prose, not a command."""
    _write(tmp_path, "经 context authoring 落图;the context backend routes it.\n")
    result = _run_against(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout


def test_allow_marker_silences(tmp_path: Path) -> None:
    _write(tmp_path, "`context write-section` 保留 <!-- allow-cli-verb: legacy example -->\n")
    result = _run_against(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout


def test_skips_fenced_code_blocks(tmp_path: Path) -> None:
    _write(tmp_path, "```\n`context write-section`\n```\n")
    result = _run_against(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
