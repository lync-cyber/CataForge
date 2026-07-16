"""``merge_hooks_config`` preserves foreign hook entries across deploys."""

from __future__ import annotations

import sys
from pathlib import Path

from cataforge.adapter.platform.hooks_config import merge_hooks_config, seed_settings_defaults

_INTERP = f'"{Path(sys.executable).as_posix()}"'
_GUARD = f"{_INTERP} -m cataforge.runtime.hook.scripts.guard_dangerous"
# Deployed-config spellings from other installs: bare ``python`` and an
# arbitrary quoted interpreter path that differs from the current one.
_GUARD_BARE = "python -m cataforge.runtime.hook.scripts.guard_dangerous"
_GUARD_OTHER_INTERP = (
    '"C:/other install/python.exe" -m cataforge.runtime.hook.scripts.guard_dangerous'
)


def _entry(command: str, matcher: str = "") -> dict:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": command}]}


def test_foreign_session_start_survives_when_cataforge_emits_none() -> None:
    existing = {
        "SessionStart": [_entry("$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.sh")],
    }
    generated = {
        "PreToolUse": [_entry(_GUARD, "Bash")],
    }

    merged = merge_hooks_config(existing, generated)

    assert merged["SessionStart"] == existing["SessionStart"]
    assert merged["PreToolUse"] == generated["PreToolUse"]


def test_owned_entries_are_replaced_not_duplicated() -> None:
    existing = {
        "PreToolUse": [_entry(_GUARD, "OldTool")],
    }
    generated = {
        "PreToolUse": [_entry(_GUARD, "Bash")],
    }

    merged = merge_hooks_config(existing, generated)

    assert merged["PreToolUse"] == generated["PreToolUse"]


def test_stale_interpreter_spellings_are_replaced_not_duplicated() -> None:
    """Deployed entries from any prior interpreter spelling are recognized as
    CataForge-owned and replaced, never left alongside the fresh entry."""
    for stale in (_GUARD_BARE, _GUARD_OTHER_INTERP, f"{_GUARD} --cataforge-platform claude-code"):
        existing = {"PreToolUse": [_entry(stale, "OldTool")]}
        generated = {"PreToolUse": [_entry(f"{_GUARD} --cataforge-platform claude-code", "Bash")]}

        merged = merge_hooks_config(existing, generated)

        assert merged["PreToolUse"] == generated["PreToolUse"], stale
        assert len(merged["PreToolUse"]) == 1, stale


def test_stale_custom_hook_spellings_are_owned() -> None:
    for stale in (
        "python .cataforge/hooks/custom/my_scan.py",
        '"C:/other install/python.exe" .cataforge/hooks/custom/my_scan.py',
    ):
        existing = {"PreToolUse": [_entry(stale, "OldTool")]}
        generated = {
            "PreToolUse": [_entry(f"{_INTERP} .cataforge/hooks/custom/my_scan.py", "Bash")]
        }

        merged = merge_hooks_config(existing, generated)

        assert merged["PreToolUse"] == generated["PreToolUse"], stale


def test_foreign_python_script_without_markers_is_preserved() -> None:
    foreign = _entry("python my_tools/precommit_hook.py", "Bash")
    existing = {"PreToolUse": [foreign]}
    generated = {"PreToolUse": [_entry(_GUARD, "Bash")]}

    merged = merge_hooks_config(existing, generated)

    assert foreign in merged["PreToolUse"]
    assert len(merged["PreToolUse"]) == 2


def test_foreign_and_owned_in_same_event_keeps_foreign() -> None:
    foreign = _entry("$CLAUDE_PROJECT_DIR/.claude/hooks/audit.sh", "Bash")
    existing = {
        "PreToolUse": [
            foreign,
            _entry(_GUARD, "OldTool"),
        ],
    }
    generated = {
        "PreToolUse": [_entry(_GUARD, "Bash")],
    }

    merged = merge_hooks_config(existing, generated)

    assert foreign in merged["PreToolUse"]
    assert merged["PreToolUse"][-1] == generated["PreToolUse"][0]
    assert len(merged["PreToolUse"]) == 2


def test_non_dict_existing_hooks_degrades_to_generated() -> None:
    generated = {"Stop": [_entry("python -m cataforge.runtime.hook.scripts.notify_done")]}

    assert merge_hooks_config(None, generated) == generated
    assert merge_hooks_config("garbage", generated) == generated


def test_empty_event_is_dropped() -> None:
    existing = {
        "PreToolUse": [_entry(_GUARD)],
    }
    # generated has no PreToolUse → the only (owned) entry is removed → event drops.
    merged = merge_hooks_config(existing, {})

    assert "PreToolUse" not in merged


def test_seed_settings_defaults_adds_missing_keys() -> None:
    data: dict = {"language": "chinese"}
    seed_settings_defaults(
        data, {"env": {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "0"}, "defaultShell": "bash"}
    )

    assert data["env"]["CLAUDE_CODE_USE_POWERSHELL_TOOL"] == "0"
    assert data["defaultShell"] == "bash"
    assert data["language"] == "chinese"


def test_seed_settings_defaults_is_set_if_absent() -> None:
    data: dict = {"env": {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "1", "OTHER": "x"}}
    seed_settings_defaults(data, {"env": {"CLAUDE_CODE_USE_POWERSHELL_TOOL": "0"}})

    # Existing leaf is preserved; sibling foreign leaf untouched.
    assert data["env"]["CLAUDE_CODE_USE_POWERSHELL_TOOL"] == "1"
    assert data["env"]["OTHER"] == "x"


def test_seed_settings_defaults_empty_is_noop() -> None:
    data: dict = {"a": 1}
    seed_settings_defaults(data, {})

    assert data == {"a": 1}
