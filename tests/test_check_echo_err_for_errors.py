"""Self-test for ``scripts/checks/check_echo_err_for_errors.py``.

The guard's value is preventing future regressions where someone adds
``click.echo("Error: ...")`` to a cli/ module without ``err=True``.
Without these tests the guard itself could silently rot — e.g. a
regex tweak that stops matching real violations would only surface
the day a real violation slipped through.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "checks" / "check_echo_err_for_errors.py"


def _run_with_test_tree(tmp_root: Path) -> subprocess.CompletedProcess[str]:
    """Run the guard against a synthetic ``src/cataforge/interface/cli/`` tree.

    The script hardcodes ``REPO_ROOT / src / cataforge / cli`` as
    ``SCAN_DIR``; monkeypatch it via a one-shot wrapper that swaps the
    constant before main(). Cleaner than spinning up an alternate
    fake repo each time.
    """
    runner = (
        "import sys, pathlib;"
        f"sys.path.insert(0, {str(REPO_ROOT / 'scripts' / 'checks')!r});"
        "import importlib.util as iu;"
        f"spec = iu.spec_from_file_location('guard', {str(SCRIPT)!r});"
        "mod = iu.module_from_spec(spec); spec.loader.exec_module(mod);"
        # Both SCAN_DIR and REPO_ROOT must point at the synthetic tree
        # so the guard's path.relative_to(REPO_ROOT) call lands cleanly.
        f"mod.SCAN_DIR = pathlib.Path({str(tmp_root)!r});"
        f"mod.REPO_ROOT = pathlib.Path({str(tmp_root)!r});"
        "sys.exit(mod.main())"
    )
    return subprocess.run(
        [sys.executable, "-c", runner],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class TestStderrEchoGuard:
    def test_passes_when_call_has_err_true(self, tmp_path: Path) -> None:
        f = tmp_path / "good.py"
        f.write_text(
            'import click\ndef cmd():\n    click.echo("Error: something broke", err=True)\n',
            encoding="utf-8",
        )
        result = _run_with_test_tree(tmp_path)
        assert result.returncode == 0, result.stderr + result.stdout

    def test_fails_when_error_message_missing_err_true(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text(
            'import click\ndef cmd():\n    click.echo("Error: something broke")\n',
            encoding="utf-8",
        )
        result = _run_with_test_tree(tmp_path)
        assert result.returncode == 1
        assert "Error: something broke" in result.stderr or "bad.py" in result.stderr

    def test_allow_marker_silences_violation(self, tmp_path: Path) -> None:
        f = tmp_path / "exempt.py"
        f.write_text(
            "import click\n"
            "def cmd():\n"
            '    click.echo("Error: x")  # allow-stdout-echo: doctor-report row\n',
            encoding="utf-8",
        )
        result = _run_with_test_tree(tmp_path)
        assert result.returncode == 0, result.stderr + result.stdout

    @pytest.mark.parametrize(
        "prefix",
        ["Error:", "ERROR:", "Cannot ", "Could not ", "Refused", "Invalid ", "Failed", "FAIL:"],
    )
    def test_detects_each_error_prefix(self, tmp_path: Path, prefix: str) -> None:
        f = tmp_path / "bad.py"
        f.write_text(
            f'import click\ndef cmd(): click.echo("{prefix}something")\n',
            encoding="utf-8",
        )
        result = _run_with_test_tree(tmp_path)
        assert result.returncode == 1, (
            f"prefix {prefix!r} must be flagged when missing err=True; stdout: {result.stdout!r}"
        )

    def test_does_not_flag_neutral_messages(self, tmp_path: Path) -> None:
        """Success-tone output stays on stdout (the default). Only
        error-toned prefixes trigger the guard — generic words like
        ``"errors:"`` inside a summary line must not false-trigger."""
        f = tmp_path / "neutral.py"
        f.write_text(
            "import click\n"
            "def cmd():\n"
            '    click.echo("OK: deployed 12 files")\n'
            '    click.echo(f"  errors: {0}")  # summary count, not an error\n'
            '    click.echo("missing:")  # lowercase prefix not in marker list\n',
            encoding="utf-8",
        )
        result = _run_with_test_tree(tmp_path)
        assert result.returncode == 0, result.stderr + result.stdout

    def test_multiline_call_with_err_true_passes(self, tmp_path: Path) -> None:
        """Real-world calls often span multiple lines; the guard must
        still detect ``err=True`` on the continuation lines."""
        f = tmp_path / "multi.py"
        f.write_text(
            "import click\n"
            "def cmd():\n"
            "    click.echo(\n"
            '        "Error: long message that wraps across lines",\n'
            "        err=True,\n"
            "    )\n",
            encoding="utf-8",
        )
        result = _run_with_test_tree(tmp_path)
        assert result.returncode == 0, result.stderr + result.stdout
