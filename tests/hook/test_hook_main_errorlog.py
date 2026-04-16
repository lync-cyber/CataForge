"""hook_main records exceptions to .cataforge/.hook-errors.jsonl.

Before C2 the decorator printed ``[HOOK-ERROR]`` to stderr and exited 0 —
Claude Code doesn't surface stderr to the user, so crashed observer hooks
were entirely invisible.  Now every crash leaves a JSONL record that
``doctor`` can surface.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import cataforge.hook.base as hook_base
from cataforge.hook.base import HOOK_ERROR_LOG_REL, hook_main


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal .cataforge/ tree that _find_framework_json can see."""
    cataforge_dir = tmp_path / ".cataforge"
    cataforge_dir.mkdir()
    (cataforge_dir / "framework.json").write_text(
        '{"version": "0.1.0", "runtime": {"platform": "claude-code"}}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_exception_logged_to_jsonl(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    @hook_main
    def crashy() -> None:
        raise RuntimeError("kaboom")

    with pytest.raises(SystemExit) as exc_info:
        crashy()
    assert exc_info.value.code == 0  # observer must never block

    log = project / HOOK_ERROR_LOG_REL
    assert log.is_file(), "hook_main must write a JSONL record on crash"

    records = [
        json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(records) == 1
    entry = records[0]
    assert entry["error_type"] == "RuntimeError"
    assert entry["error"] == "kaboom"
    assert entry["func"] == "crashy"
    assert "traceback" in entry
    assert "kaboom" in entry["traceback"]


def test_systemexit_propagates(project: Path) -> None:
    """block hooks that call sys.exit(2) must not be logged or suppressed."""

    @hook_main
    def blocker() -> None:
        raise SystemExit(2)

    with pytest.raises(SystemExit) as exc_info:
        blocker()
    assert exc_info.value.code == 2

    log = project / HOOK_ERROR_LOG_REL
    assert not log.exists(), "SystemExit is not an error — no log entry expected"


def test_log_rotates_when_large(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runaway crash loops must not grow the log without bound."""
    log = project / HOOK_ERROR_LOG_REL
    log.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(hook_base, "HOOK_ERROR_LOG_MAX_BYTES", 128)
    log.write_text("x" * 512, encoding="utf-8")  # pre-seed over threshold

    @hook_main
    def crashy() -> None:
        raise ValueError("rotate me")

    with pytest.raises(SystemExit):
        crashy()

    # Old content rolled into .1; new record lives in the fresh file.
    bak = log.with_suffix(log.suffix + ".1")
    assert bak.is_file()
    new_content = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(new_content) == 1
    entry = json.loads(new_content[0])
    assert entry["error"] == "rotate me"
