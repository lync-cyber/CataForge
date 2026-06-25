"""doctor shell-preference check — Windows-only WARN, never gates (returns 0)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from cataforge.core.config import ConfigManager
from cataforge.interface.cli.doctor import shell_preference
from cataforge.interface.cli.doctor.shell_preference import check_shell_preference


def _project(tmp_path: Path, settings: dict | None = None) -> Path:
    (tmp_path / ".cataforge").mkdir()
    (tmp_path / ".cataforge" / "framework.json").write_text(
        '{"version": "0.1.0"}', encoding="utf-8"
    )
    if settings is not None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    return tmp_path


def test_non_windows_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    root = _project(tmp_path, {"env": {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "0"}})

    rc = check_shell_preference(ConfigManager(root))
    assert rc == 0
    assert "skipped" in capsys.readouterr().out


def test_windows_prefer_bash_without_git_bash_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("CLAUDE_CODE_GIT_BASH_PATH", raising=False)
    monkeypatch.setattr(shell_preference.shutil, "which", lambda _: None)
    root = _project(tmp_path, {"env": {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "0"}})

    rc = check_shell_preference(ConfigManager(root))
    out = capsys.readouterr().out
    assert rc == 0  # advisory only
    assert "WARN" in out
    assert "Git for Windows" in out


def test_windows_prefer_bash_with_git_bash_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    bash = tmp_path / "bash.exe"
    bash.write_text("", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CODE_GIT_BASH_PATH", str(bash))
    root = _project(tmp_path, {"env": {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "0"}})

    rc = check_shell_preference(ConfigManager(root))
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_windows_powershell_allowed_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    root = _project(tmp_path, {"env": {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "1"}})

    rc = check_shell_preference(ConfigManager(root))
    assert rc == 0
    assert "skipped" in capsys.readouterr().out


def test_windows_without_settings_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    root = _project(tmp_path, settings=None)

    rc = check_shell_preference(ConfigManager(root))
    assert rc == 0
    assert "skipped" in capsys.readouterr().out
