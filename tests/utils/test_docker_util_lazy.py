"""Tests for docker_util._platform() lazy evaluation.

The module-level PLATFORM constant was removed; _platform() now calls
detect_platform() on every invocation so monkeypatching sys.platform
takes effect after import.
"""

from __future__ import annotations

import sys


class TestDockerUtilLazy:
    def test_platform_reflects_monkeypatched_win32(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        from cataforge.utils.docker_util import _platform

        result = _platform()
        assert result == "windows"

    def test_platform_reflects_monkeypatched_linux(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "linux")
        from cataforge.utils.docker_util import _platform

        result = _platform()
        assert result == "linux"

    def test_platform_reflects_monkeypatched_darwin(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "darwin")
        from cataforge.utils.docker_util import _platform

        result = _platform()
        assert result == "darwin"

    def test_platform_changes_across_calls(self, monkeypatch) -> None:
        from cataforge.utils.docker_util import _platform

        monkeypatch.setattr(sys, "platform", "win32")
        r1 = _platform()

        monkeypatch.setattr(sys, "platform", "linux")
        r2 = _platform()

        assert r1 != r2

    def test_module_getattr_platform_compat(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "platform", "win32")
        import cataforge.utils.docker_util as du

        result = du.PLATFORM
        assert result == "windows"
