"""Typed schema for platform ``profile.yaml`` files.

A platform profile is loaded once at adapter construction and read through
many ``PlatformAdapter`` properties.  Modelling it as pydantic moves malformed
input from a runtime ``AttributeError`` / silent wrong-type to a load-time
``ValidationError`` that names the offending field.

Design constraints:

* Every section is an **optional** field carrying the default the adapter
  property expects, so a profile that omits a section still validates and the
  property returns the same fallback value.
* ``extra="forbid"`` on the top level and the structurally-stable nested
  models catches typos / drift.  Deep, rarely-read blocks whose shape varies
  per platform (``instruction_file.targets[].section_policy``,
  ``context_injection`` …) stay raw ``dict[str, Any]`` so all four real
  profiles validate without enumerating every leaf key.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_FORBID = ConfigDict(extra="forbid")


class AgentDefinition(BaseModel):
    model_config = _FORBID

    format: str | None = None
    scan_dirs: list[str] = Field(default_factory=list)
    needs_deploy: bool = True


class SkillDefinition(BaseModel):
    model_config = _FORBID

    target_dir: str | None = None
    needs_deploy: bool = False


class CommandDefinition(BaseModel):
    model_config = _FORBID

    target_dir: str | None = None
    needs_deploy: bool = False


class RulesConfig(BaseModel):
    model_config = _FORBID

    cross_platform_mirror: bool = False


class AgentConfig(BaseModel):
    model_config = _FORBID

    supported_fields: list[str] = Field(default_factory=list)
    memory_scopes: list[str] = Field(default_factory=list)
    isolation_modes: list[str] = Field(default_factory=list)


class InstructionFile(BaseModel):
    model_config = _FORBID

    reads_claude_md: bool = False
    # ``targets[]`` entries carry a stable ``type``/``path`` plus a deeply
    # nested, per-platform ``section_policy`` block — kept as raw dicts so the
    # adapter's ``instruction_targets`` property keeps returning ``list[dict]``.
    targets: list[dict[str, Any]] = Field(default_factory=list)
    additional_outputs: list[dict[str, Any]] = Field(default_factory=list)


class Dispatch(BaseModel):
    model_config = _FORBID

    tool_name: str | None = None
    is_async: bool = False
    params: list[str] = Field(default_factory=list)


class Hooks(BaseModel):
    model_config = _FORBID

    config_format: str | None = None
    config_path: str | None = None
    entry_type: str | None = None
    event_map: dict[str, str | None] = Field(default_factory=dict)
    matcher_map: dict[str, str | None] = Field(default_factory=dict)
    tool_overrides: dict[str, str] = Field(default_factory=dict)
    degradation: dict[str, str] = Field(default_factory=dict)


class ModelRouting(BaseModel):
    model_config = _FORBID

    available_models: list[str] = Field(default_factory=list)
    per_agent_model: bool = False
    user_resolved: bool = False
    tier_map: dict[str, str | None] = Field(default_factory=dict)


class PlatformProfile(BaseModel):
    """Validated representation of a single ``profile.yaml``."""

    model_config = _FORBID

    platform_id: str | None = None
    display_name: str | None = None
    version_tested: str | None = None

    tool_map: dict[str, str | None] = Field(default_factory=dict)
    extended_capabilities: dict[str, str | None] = Field(default_factory=dict)

    agent_definition: AgentDefinition = Field(default_factory=AgentDefinition)
    skill_definition: SkillDefinition = Field(default_factory=SkillDefinition)
    command_definition: CommandDefinition = Field(default_factory=CommandDefinition)
    rules: RulesConfig = Field(default_factory=RulesConfig)
    agent_config: AgentConfig = Field(default_factory=AgentConfig)
    instruction_file: InstructionFile = Field(default_factory=InstructionFile)
    dispatch: Dispatch = Field(default_factory=Dispatch)
    hooks: Hooks = Field(default_factory=Hooks)

    # ``features``/``permissions`` are flat enough to keep as typed dicts.
    features: dict[str, bool] = Field(default_factory=dict)
    permissions: dict[str, Any] = Field(default_factory=dict)

    model_routing: ModelRouting = Field(default_factory=ModelRouting)

    # ``context_injection`` is a deep, per-platform tree (auto_injection /
    # inline_file_syntax / rules_distribution).  Kept raw so the adapter's
    # ``context_injection`` property keeps returning a plain ``dict``.
    context_injection: dict[str, Any] = Field(default_factory=dict)
