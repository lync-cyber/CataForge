"""Typed schema for the canonical ``hooks.yaml`` hook specification.

``load_hooks_spec`` validates the raw mapping against :class:`HooksSpec` so a
malformed spec (``schema_version`` that is not an int, ``hooks`` that is not a
mapping of event → entry list, a hook entry missing ``script`` …) fails at load
time with a ``pydantic.ValidationError`` naming the offending field instead of
surfacing as a ``KeyError`` / ``AttributeError`` deep in the platform bridge.

Hook entries stay permissive (``extra="allow"``) because the v2 matcher fields
(``matcher_file_pattern`` / ``matcher_command_pattern`` / ``matcher_agent_id``)
are optional and plugin-provided entries may carry their own keys. The
top-level spec is strict so retired sections cannot silently survive a schema
upgrade.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HookEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    script: str
    type: str = "observe"
    description: str = ""
    matcher_capability: str | None = None
    safety_critical: bool = False
    matcher_agent_id: list[str] = Field(default_factory=list)
    matcher_file_pattern: str | None = None
    matcher_command_pattern: str | None = None


class HooksSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    hooks: dict[str, list[HookEntry]] = Field(default_factory=dict)
