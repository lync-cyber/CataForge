"""User-authored hook scripts via ``script: custom:<name>`` (C7).

Users can drop their own hooks into ``.cataforge/hooks/custom/<name>.py``
and reference them from ``hooks.yaml`` with a ``custom:`` prefix.  The
bridge rewrites the invocation command to run the file directly instead
of going through the ``cataforge.runtime.hook.scripts`` package namespace.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from cataforge.runtime.hook.bridge import generate_platform_hooks


class _StubAdapter:
    platform_id = "test"
    hook_entry_type = "command"

    def get_tool_map(self) -> dict[str, str | None]:
        return {"shell_exec": "Bash"}

    @property
    def hook_event_map(self) -> dict[str, str | None]:
        return {"PreToolUse": "PreToolUse"}

    @property
    def hook_degradation(self) -> dict[str, str]:
        return {"custom:my_scan": "native"}

    def get_hook_command_template(self) -> str:
        return "python -m cataforge.runtime.hook.scripts.{module}"


def test_custom_hook_uses_file_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    import cataforge.runtime.hook.bridge as bridge

    spec = {
        "hooks": {
            "PreToolUse": [
                {
                    "script": "custom:my_scan",
                    "matcher_capability": "shell_exec",
                    "type": "observe",
                }
            ]
        }
    }
    monkeypatch.setattr(bridge, "load_hooks_spec", lambda _p=None: spec)

    hooks, warnings = generate_platform_hooks(_StubAdapter())

    assert warnings == []
    pre = hooks["PreToolUse"]
    cmd = pre[0]["hooks"][0]["command"]
    # Custom scripts live in the project — the generated command references
    # the file directly rather than going through the ``-m`` package path,
    # and runs under the deploying interpreter.
    quoted_interp = f'"{Path(sys.executable).as_posix()}"'
    assert cmd == (f"{quoted_interp} .cataforge/hooks/custom/my_scan.py --cataforge-platform test")
    # And the module-style command must NOT be used for customs.
    assert "cataforge.runtime.hook.scripts" not in cmd
