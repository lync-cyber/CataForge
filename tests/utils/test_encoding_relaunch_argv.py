"""Regression tests for UTF-8 relaunch environment identity."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, cast

import pytest

from cataforge.utils import encoding


def test_windows_relaunch_uses_active_environment_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """uv trampolines may expose the base Python as ``orig_argv[0]``."""
    base_python = r"C:\Python311\python.exe"
    tool_python = r"C:\uv\tools\cataforge\Scripts\python.exe"
    launcher = r"C:\uv\tools\cataforge\Scripts\cataforge.exe"
    captured: dict[str, Any] = {}

    monkeypatch.setattr("cataforge.utils.encoding.sys.platform", "win32")
    monkeypatch.setattr("cataforge.utils.encoding.sys.executable", tool_python)
    monkeypatch.setattr(
        "cataforge.utils.encoding.sys.orig_argv", [base_python, launcher, "--version"]
    )
    monkeypatch.setattr("cataforge.utils.encoding.sys.flags", type("Flags", (), {"utf8_mode": 0})())
    monkeypatch.setattr(
        "cataforge.utils.encoding.sys.modules",
        {name: module for name, module in sys.modules.items() if name != "pytest"},
    )
    for name in list(os.environ):
        if name.startswith("PYTEST_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(encoding, "_preferred_encoding_is_utf8", lambda: False)

    def fake_run(argv: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["env"] = env
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr("cataforge.utils.encoding.subprocess.run", fake_run)

    with pytest.raises(SystemExit) as exc:
        encoding.ensure_utf8()

    assert exc.value.code == 0
    assert captured["argv"] == [tool_python, launcher, "--version"]
    captured_env = cast(dict[str, str], captured["env"])
    assert captured_env["PYTHONUTF8"] == "1"
