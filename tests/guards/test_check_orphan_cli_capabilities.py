"""Self-test for ``scripts/checks/check_orphan_cli_capabilities.py``.

The guard fails when a top-level CLI command is neither referenced by a
prompt asset nor declared in EXEMPT — catching a capability built but never
wired into the agentic workflow. The logic tests stub ``cli_commands`` /
``EXEMPT`` so they don't depend on the live CLI tree; one integration test
runs the real guard against the repo so the EXEMPT registry stays complete
as commands are added.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "checks" / "check_orphan_cli_capabilities.py"


def _run(tmp_root: Path, commands: dict[str, tuple[str, ...]], exempt: dict[str, str], body: str):
    """Run the guard with stubbed commands/EXEMPT and SCAN_GLOBS at *tmp_root*."""
    (tmp_root / "SKILL.md").write_text(body, encoding="utf-8")
    runner = (
        "import sys, pathlib;"
        f"sys.path.insert(0, {str(REPO_ROOT / 'scripts' / 'checks')!r});"
        "import importlib.util as iu;"
        f"spec = iu.spec_from_file_location('guard', {str(SCRIPT)!r});"
        "mod = iu.module_from_spec(spec); spec.loader.exec_module(mod);"
        f"mod.REPO_ROOT = pathlib.Path({str(tmp_root)!r});"
        f"mod.SCAN_GLOBS = [(pathlib.Path({str(tmp_root)!r}), '**/*.md')];"
        f"mod.cli_commands = lambda: {commands!r};"
        f"mod.EXEMPT = {exempt!r};"
        "sys.exit(mod.main())"
    )
    return subprocess.run(
        [sys.executable, "-c", runner], capture_output=True, text=True, encoding="utf-8"
    )


def test_passes_when_command_referenced(tmp_path: Path) -> None:
    result = _run(tmp_path, {"viz": ("framework",)}, {}, "看编排图用 `cataforge viz framework`。\n")
    assert result.returncode == 0, result.stderr + result.stdout


def test_flags_orphan_command(tmp_path: Path) -> None:
    result = _run(tmp_path, {"viz": ()}, {}, "无关散文，未引用任何命令。\n")
    assert result.returncode == 1
    assert "orphan" in result.stderr and "viz" in result.stderr


def test_exempt_silences_orphan(tmp_path: Path) -> None:
    result = _run(tmp_path, {"hook": ()}, {"hook": "infra command"}, "无引用。\n")
    assert result.returncode == 0, result.stderr + result.stdout


def test_backtick_subcommand_counts_as_reference(tmp_path: Path) -> None:
    result = _run(tmp_path, {"viz": ("tasks",)}, {}, "依赖图走 `viz tasks --format mermaid`。\n")
    assert result.returncode == 0, result.stderr + result.stdout


def test_redundant_exemption_flagged(tmp_path: Path) -> None:
    result = _run(tmp_path, {"viz": ()}, {"viz": "stale"}, "现在引用了 `cataforge viz`。\n")
    assert result.returncode == 1
    assert "remove it from EXEMPT" in result.stderr


def test_stale_exemption_flagged(tmp_path: Path) -> None:
    result = _run(tmp_path, {"viz": ("framework",)}, {"gone": "x"}, "`cataforge viz framework`\n")
    assert result.returncode == 1
    assert "no longer a CLI command" in result.stderr


def test_real_repo_has_no_orphans() -> None:
    """The committed EXEMPT registry covers every unreferenced CLI command."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr + result.stdout
