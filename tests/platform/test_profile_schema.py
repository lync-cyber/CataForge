"""Load-time validation contract for :class:`PlatformProfile`.

Locks the T-1 guarantee: a malformed ``profile.yaml`` fails when the profile is
loaded (``pydantic.ValidationError`` naming the offending field) instead of as
an ``AttributeError`` deep in an adapter property at deploy time — while every
shipped profile still validates and a profile that merely omits an optional
section keeps loading with the legacy default.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cataforge.adapter.platform.profile_schema import PlatformProfile
from cataforge.adapter.platform.registry import BUILTIN_PLATFORM_IDS, load_profile


@pytest.mark.parametrize("platform_id", BUILTIN_PLATFORM_IDS)
def test_shipped_profile_validates(platform_id: str) -> None:
    """Every shipped profile loads without raising."""
    profile = load_profile(platform_id)
    assert isinstance(profile, PlatformProfile)
    assert profile.platform_id == platform_id


def test_claude_code_key_fields_preserved() -> None:
    """A spot-check that typed access returns the same values as the YAML."""
    profile = load_profile("claude-code")
    assert profile.tool_map["file_read"] == "Read"
    assert profile.hooks.config_format == "json"
    assert profile.hooks.config_path == ".claude/settings.json"
    assert profile.model_routing.tier_map["heavy"] == "opus"
    assert profile.agent_definition.scan_dirs == [".claude/agents"]


def test_codex_toml_and_overrides_preserved() -> None:
    """Codex's divergent shape (TOML hooks matcher overrides) survives."""
    profile = load_profile("codex")
    assert profile.agent_definition.format == "toml"
    assert profile.hooks.tool_overrides == {"shell_exec": "Bash"}
    assert profile.model_routing.user_resolved is False


def test_opencode_plugin_hooks_shape_preserved() -> None:
    """OpenCode omits hooks.config_path and uses empty matcher maps."""
    profile = load_profile("opencode")
    assert profile.hooks.config_format == "plugin"
    assert profile.hooks.config_path is None
    assert profile.hooks.matcher_map == {}
    assert profile.model_routing.tier_map == {}


# ---- malformed profiles fail at load with a field-level error ----------


def test_wrong_type_tool_map_rejected() -> None:
    """``tool_map`` authored as a string (not a mapping) is a load error."""
    with pytest.raises(ValidationError) as exc:
        PlatformProfile.model_validate({"platform_id": "x", "tool_map": "Read"})
    assert "tool_map" in str(exc.value)


def test_wrong_type_nested_field_rejected() -> None:
    """A nested field with the wrong type names the nested field."""
    with pytest.raises(ValidationError) as exc:
        PlatformProfile.model_validate(
            {"platform_id": "x", "agent_definition": {"needs_deploy": "yes-please"}}
        )
    assert "needs_deploy" in str(exc.value)


def test_features_wrong_value_type_rejected() -> None:
    """``features`` values must be booleans."""
    with pytest.raises(ValidationError) as exc:
        PlatformProfile.model_validate({"platform_id": "x", "features": {"cloud_agents": "maybe"}})
    assert "features" in str(exc.value)


def test_unknown_top_level_key_rejected() -> None:
    """``extra='forbid'`` catches a misspelled / drifted top-level section."""
    with pytest.raises(ValidationError) as exc:
        PlatformProfile.model_validate({"platform_id": "x", "tool_maps": {}})
    assert "tool_maps" in str(exc.value)


def test_unknown_nested_key_rejected() -> None:
    """Forbid extends to structurally-stable nested models."""
    with pytest.raises(ValidationError) as exc:
        PlatformProfile.model_validate({"platform_id": "x", "hooks": {"config_formatt": "json"}})
    assert "config_formatt" in str(exc.value)


# ---- omitting optional sections keeps loading with defaults ------------


def test_minimal_profile_uses_defaults() -> None:
    """A profile with only ``platform_id`` validates; absent sections take
    their legacy defaults rather than crashing at load."""
    profile = PlatformProfile.model_validate({"platform_id": "minimal"})
    assert profile.tool_map == {}
    assert profile.extended_capabilities == {}
    assert profile.agent_definition.needs_deploy is True
    assert profile.skill_definition.needs_deploy is False
    assert profile.command_definition.needs_deploy is False
    assert profile.instruction_file.reads_claude_md is False
    assert profile.instruction_file.targets == []
    assert profile.hooks.config_format is None
    assert profile.hooks.event_map == {}
    assert profile.features == {}
    assert profile.permissions == {}
    assert profile.model_routing.available_models == []
    assert profile.model_routing.tier_map == {}
    assert profile.context_injection == {}


def test_empty_profile_validates() -> None:
    """An entirely empty mapping validates (all fields optional)."""
    profile = PlatformProfile.model_validate({})
    assert profile.platform_id is None
