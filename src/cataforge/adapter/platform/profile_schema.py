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

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_FORBID = ConfigDict(extra="forbid")


class AgentDefinition(BaseModel):
    model_config = _FORBID

    format: str | None = None
    scan_dirs: list[str] = Field(default_factory=list)
    needs_deploy: bool = True
    # Deploy strategy knobs consumed by ``runtime.deploy.steps.agents``.
    # ``layout`` ``flat`` writes one ``<name><suffix>`` per agent; ``subdir``
    # reproduces the ``<name>/AGENT.md`` tree. ``target_rel`` overrides the
    # flat target dir when the platform does not surface it via ``scan_dirs``.
    layout: str = "subdir"
    target_rel: str | None = None
    file_suffix: str = ".md"
    head_signature: str = "name: {stem}"
    head_read_size: int = 512
    prune_legacy_subdirs: bool = False


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
    tool_policy: Literal["allow_deny", "allow_only", "inherit_only"] = "allow_deny"


class AvailabilityClause(BaseModel):
    """One sufficient runtime context for a capability to be available."""

    model_config = _FORBID

    thread_scopes: list[Literal["root", "subagent"]] = Field(default_factory=list)
    collaboration_modes: list[Literal["plan", "default"]] = Field(default_factory=list)
    required_features: list[Literal["default_mode_request_user_input"]] = Field(
        default_factory=list
    )


class CapabilityAvailability(BaseModel):
    """Disjunction of availability clauses; an empty list means unconditional."""

    model_config = _FORBID

    any_of: list[AvailabilityClause] = Field(default_factory=list)


class CapabilityBinding(BaseModel):
    """Typed mapping from a CataForge capability to a platform surface."""

    model_config = _FORBID

    tool: str | None = None
    kind: Literal["native", "replacement", "unsupported"] = "native"
    availability: CapabilityAvailability = Field(default_factory=CapabilityAvailability)
    hook_matchers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_tool_contract(self) -> CapabilityBinding:
        if self.kind == "unsupported" and self.tool is not None:
            raise ValueError("unsupported capability must not declare a tool")
        if self.kind != "unsupported" and self.tool is None:
            raise ValueError(f"{self.kind} capability must declare a tool")
        return self


class CapabilityContext(BaseModel):
    """Runtime facts used to resolve a conditional capability binding."""

    model_config = _FORBID

    thread_scope: Literal["root", "subagent"] | None = None
    collaboration_mode: Literal["plan", "default"] | None = None
    enabled_features: set[str] = Field(default_factory=set)


class CapabilityResolution(BaseModel):
    """Resolved support state for one capability and optional runtime context."""

    model_config = _FORBID

    capability: str
    tool: str | None
    status: Literal["native", "conditional", "replacement", "unsupported"]
    available: bool | None
    hook_matchers: list[str] = Field(default_factory=list)
    reason: str | None = None


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


class HookFallback(BaseModel):
    model_config = _FORBID

    strategy: Literal["rules_injection", "prompt_instruction", "prompt_checklist", "skip"] = "skip"
    coverage: Literal["equivalent", "partial", "none"] = "none"
    reason: str = ""
    asset: str | None = None
    content: str = ""


class HookPolicy(BaseModel):
    model_config = _FORBID

    mode: Literal["native", "hybrid", "degraded", "unsupported"] = "native"
    fallback: HookFallback | None = None

    @model_validator(mode="after")
    def _validate_fallback_contract(self) -> HookPolicy:
        if self.mode in {"hybrid", "degraded"} and self.fallback is None:
            raise ValueError(f"{self.mode} hook policy requires fallback")
        if (
            self.fallback is not None
            and self.fallback.coverage == "equivalent"
            and self.fallback.strategy == "skip"
        ):
            raise ValueError("skip fallback cannot claim equivalent coverage")
        return self


class Hooks(BaseModel):
    model_config = _FORBID

    config_format: str | None = None
    config_path: str | None = None
    entry_type: str | None = None
    event_map: dict[str, str | None] = Field(default_factory=dict)
    policies: dict[str, HookPolicy] = Field(default_factory=dict)


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

    tool_map: dict[str, CapabilityBinding] = Field(default_factory=dict)
    extended_capabilities: dict[str, CapabilityBinding] = Field(default_factory=dict)

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

    # Framework-owned default keys seeded into the platform settings file at
    # deploy time (set-if-absent, so a user override survives redeploy). Shape
    # is the platform's own settings schema — e.g. Claude Code seeds
    # ``env``/``defaultShell`` to prefer Git Bash over the PowerShell tool.
    settings_defaults: dict[str, Any] = Field(default_factory=dict)

    model_routing: ModelRouting = Field(default_factory=ModelRouting)

    # ``context_injection`` is a deep, per-platform tree (auto_injection /
    # inline_file_syntax / rules_distribution).  Kept raw so the adapter's
    # ``context_injection`` property keeps returning a plain ``dict``.
    context_injection: dict[str, Any] = Field(default_factory=dict)
