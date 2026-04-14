"""Hook bridge skip diagnostics (M5)."""

from __future__ import annotations

import logging

import pytest

from cataforge.hook.bridge import generate_platform_hooks


class _StubAdapter:
    """Minimal surface used by ``generate_platform_hooks``."""

    platform_id = "test"

    def __init__(
        self,
        *,
        tool_map: dict[str, str | None] | None = None,
        event_map: dict[str, str | None] | None = None,
        degradation: dict[str, str] | None = None,
    ) -> None:
        self._tool_map = tool_map or {}
        self._event_map = event_map or {}
        self._degradation = degradation or {"guard_dangerous": "native"}

    def get_tool_map(self) -> dict[str, str | None]:
        return dict(self._tool_map)

    @property
    def hook_event_map(self) -> dict[str, str | None]:
        return dict(self._event_map)

    @property
    def hook_degradation(self) -> dict[str, str]:
        return dict(self._degradation)

    def get_hook_command_template(self) -> str:
        return "python -m cataforge.hook.scripts.{module}"


def test_skip_logs_unmapped_event(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cataforge.hook.bridge as bridge

    spec = {
        "hooks": {
            "NoSuchEvent": [
                {
                    "script": "guard_dangerous.py",
                    "matcher_capability": "file_read",
                    "type": "observe",
                }
            ]
        }
    }
    monkeypatch.setattr(bridge, "load_hooks_spec", lambda _p=None: spec)

    with caplog.at_level(logging.DEBUG, logger="cataforge.hook.bridge"):
        generate_platform_hooks(
            _StubAdapter(
                tool_map={"file_read": "Read"},
                event_map={"PreToolUse": "pre"},
            )
        )

    assert any("no platform mapping" in r.message for r in caplog.records)


def test_skip_logs_missing_tool_mapping(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cataforge.hook.bridge as bridge

    spec = {
        "hooks": {
            "PreToolUse": [
                {
                    "script": "guard_dangerous.py",
                    "matcher_capability": "unknown_capability",
                    "type": "observe",
                }
            ]
        }
    }
    monkeypatch.setattr(bridge, "load_hooks_spec", lambda _p=None: spec)

    with caplog.at_level(logging.DEBUG, logger="cataforge.hook.bridge"):
        generate_platform_hooks(
            _StubAdapter(
                tool_map={},
                event_map={"PreToolUse": "pre"},
            )
        )

    assert any("no tool mapping" in r.message for r in caplog.records)


def test_skip_logs_non_native_degradation(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cataforge.hook.bridge as bridge

    spec = {
        "hooks": {
            "PreToolUse": [
                {
                    "script": "guard_dangerous.py",
                    "matcher_capability": "file_read",
                    "type": "observe",
                }
            ]
        }
    }
    monkeypatch.setattr(bridge, "load_hooks_spec", lambda _p=None: spec)

    with caplog.at_level(logging.DEBUG, logger="cataforge.hook.bridge"):
        generate_platform_hooks(
            _StubAdapter(
                tool_map={"file_read": "Read"},
                event_map={"PreToolUse": "pre"},
                degradation={"guard_dangerous": "degraded"},
            )
        )

    assert any("need 'native'" in r.message for r in caplog.records)
