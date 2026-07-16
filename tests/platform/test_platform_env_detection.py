"""Characterization: platform detection from env vars.

``detect_platform`` (adapter registry) and ``get_platform`` (hook base) share
the ``CATAFORGE_PLATFORM`` → IDE-env prefix, extracted into ``platform_from_env``.
These lock the env-sniffing precedence across both detectors.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from cataforge.adapter.platform.registry import detect_platform
from cataforge.runtime.hook.base import get_platform

_PLATFORM_ENV = ("CATAFORGE_PLATFORM", "CURSOR_PROJECT_DIR", "CODEX_HOME", "CLAUDE_PROJECT_DIR")
_DETECTORS: list[Callable[[], str]] = [detect_platform, get_platform]


@pytest.fixture
def clean_platform_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _PLATFORM_ENV:
        monkeypatch.delenv(var, raising=False)


@pytest.mark.usefixtures("clean_platform_env")
@pytest.mark.parametrize("detector", _DETECTORS)
def test_explicit_override_wins(
    detector: Callable[[], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CATAFORGE_PLATFORM", "custom-plat")
    monkeypatch.setenv("CURSOR_PROJECT_DIR", "/x")  # lower priority — ignored
    assert detector() == "custom-plat"


@pytest.mark.usefixtures("clean_platform_env")
@pytest.mark.parametrize("detector", _DETECTORS)
@pytest.mark.parametrize(
    ("env_var", "expected"),
    [
        ("CURSOR_PROJECT_DIR", "cursor"),
        ("CLAUDE_PROJECT_DIR", "claude-code"),
    ],
)
def test_ide_env_detection(
    detector: Callable[[], str],
    env_var: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(env_var, "/some/path")
    assert detector() == expected


@pytest.mark.usefixtures("clean_platform_env")
@pytest.mark.parametrize("detector", _DETECTORS)
def test_default_when_no_env_signal_or_framework_json(
    detector: Callable[[], str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    assert detector() == "claude-code"
