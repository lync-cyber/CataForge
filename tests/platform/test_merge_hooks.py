"""``merge_hooks_config`` preserves foreign hook entries across deploys."""

from __future__ import annotations

from cataforge.adapter.platform.hooks_config import merge_hooks_config, seed_settings_defaults

_OWNED = ("python -m cataforge.runtime.hook.scripts.", "python .cataforge/hooks/custom/")
_GUARD = "python -m cataforge.runtime.hook.scripts.guard_dangerous"


def _entry(command: str, matcher: str = "") -> dict:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": command}]}


def test_foreign_session_start_survives_when_cataforge_emits_none() -> None:
    existing = {
        "SessionStart": [_entry("$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.sh")],
    }
    generated = {
        "PreToolUse": [_entry(_GUARD, "Bash")],
    }

    merged = merge_hooks_config(existing, generated, _OWNED)

    assert merged["SessionStart"] == existing["SessionStart"]
    assert merged["PreToolUse"] == generated["PreToolUse"]


def test_owned_entries_are_replaced_not_duplicated() -> None:
    existing = {
        "PreToolUse": [_entry(_GUARD, "OldTool")],
    }
    generated = {
        "PreToolUse": [_entry(_GUARD, "Bash")],
    }

    merged = merge_hooks_config(existing, generated, _OWNED)

    assert merged["PreToolUse"] == generated["PreToolUse"]


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

    merged = merge_hooks_config(existing, generated, _OWNED)

    assert foreign in merged["PreToolUse"]
    assert merged["PreToolUse"][-1] == generated["PreToolUse"][0]
    assert len(merged["PreToolUse"]) == 2


def test_custom_prefix_entries_are_owned() -> None:
    existing = {
        "PreToolUse": [_entry("python .cataforge/hooks/custom/my_scan.py", "OldTool")],
    }
    generated = {
        "PreToolUse": [_entry("python .cataforge/hooks/custom/my_scan.py", "Bash")],
    }

    merged = merge_hooks_config(existing, generated, _OWNED)

    assert merged["PreToolUse"] == generated["PreToolUse"]


def test_non_dict_existing_hooks_degrades_to_generated() -> None:
    generated = {"Stop": [_entry("python -m cataforge.runtime.hook.scripts.notify_done")]}

    assert merge_hooks_config(None, generated, _OWNED) == generated
    assert merge_hooks_config("garbage", generated, _OWNED) == generated


def test_empty_event_is_dropped() -> None:
    existing = {
        "PreToolUse": [_entry(_GUARD)],
    }
    # generated has no PreToolUse → the only (owned) entry is removed → event drops.
    merged = merge_hooks_config(existing, {}, _OWNED)

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
