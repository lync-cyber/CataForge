"""Hook bridge skip diagnostics.

As of the C1 improvements, the bridge surfaces ``skip`` events as warnings
in its return value (instead of only writing them to a debug log).  These
tests lock that behaviour in.
"""

from __future__ import annotations

import pytest

from cataforge.adapter.platform.profile_schema import HookPolicy
from cataforge.runtime.hook.bridge import generate_platform_hooks


class _StubAdapter:
    """Minimal surface used by ``generate_platform_hooks``."""

    platform_id = "test"
    hook_entry_type = "command"

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

    @property
    def hook_event_map(self) -> dict[str, str | None]:
        return dict(self._event_map)

    def get_hook_policy(self, hook_name: str) -> HookPolicy:
        mode = self._degradation.get(hook_name, "native")
        if mode == "degraded":
            return HookPolicy(
                mode="degraded",
                fallback={
                    "strategy": "skip",
                    "coverage": "none",
                    "reason": "test",
                },
            )
        return HookPolicy(mode=mode)

    def resolve_hook_matcher(self, capability: str) -> str | None:
        return self._tool_map.get(capability)

    def get_hook_command_template(self) -> str:
        return "python -m cataforge.runtime.hook.scripts.{module}"


def test_warns_on_unmapped_event(monkeypatch: pytest.MonkeyPatch) -> None:
    import cataforge.runtime.hook.bridge as bridge

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

    _hooks, warnings = generate_platform_hooks(
        _StubAdapter(
            tool_map={"file_read": "Read"},
            event_map={"PreToolUse": "pre"},
        )
    )
    assert any("no platform mapping" in w for w in warnings), warnings


def test_warns_on_missing_tool_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    import cataforge.runtime.hook.bridge as bridge

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

    _hooks, warnings = generate_platform_hooks(
        _StubAdapter(
            tool_map={},
            event_map={"PreToolUse": "pre"},
        )
    )
    assert any("no tool mapping" in w for w in warnings), warnings


def test_warns_on_non_native_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
    import cataforge.runtime.hook.bridge as bridge

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

    _hooks, warnings = generate_platform_hooks(
        _StubAdapter(
            tool_map={"file_read": "Read"},
            event_map={"PreToolUse": "pre"},
            degradation={"guard_dangerous": "degraded"},
        )
    )
    assert any("degraded" in w and "guard_dangerous" in w for w in warnings), warnings
