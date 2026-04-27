"""MCP server declarations (YAML / entry_points).

Strict-mode policy: ``MCPServerState`` opts into ``strict=True`` because
its inputs come exclusively from cataforge-controlled state files (JSON
round-tripped via ``model_dump`` → ``model_validate``); every value
preserves type fidelity. ``MCPServerSpec`` and ``HealthCheckSpec`` stay
non-strict because their inputs come from third-party YAML manifests
where type-loose authoring (``port: "8080"``) is common; coercing rather
than rejecting keeps integration smooth. ``validate_assignment=True``
applies to all models so post-construction mutation cannot bypass
validation.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self


class HealthCheckSpec(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    type: Literal["http", "tcp", "command"] = "http"
    target: str = ""
    interval_seconds: int = 30
    timeout_seconds: int = 5
    retries: int = 3


class MCPServerSpec(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        validate_assignment=True,
    )

    id: str
    name: str = ""
    description: str = ""
    version: str = "0.0.0"

    transport: str = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)

    @field_validator("env", mode="before")
    @classmethod
    def _stringify_env(cls, v: Any) -> dict[str, str]:
        if not v:
            return {}
        if not isinstance(v, dict):
            return {}
        return {str(k): str(val) for k, val in v.items()}

    requires: list[str] = Field(default_factory=list)
    pip_depends: list[str] = Field(default_factory=list)
    npm_depends: list[str] = Field(default_factory=list)

    platform_config: dict[str, dict[str, Any]] = Field(default_factory=dict)
    health_check: HealthCheckSpec | None = None

    category: str = "general"
    auto_start: bool = False
    optional: bool = True

    @model_validator(mode="after")
    def _default_name(self) -> Self:
        if not (self.name or "").strip():
            # mutate-in-place: pydantic v2 requires `self` be returned from
            # after-validators, not a fresh copy (UserWarning otherwise).
            object.__setattr__(self, "name", self.id)
        return self


class MCPServerState(BaseModel):
    """Internal MCP lifecycle state — strict-mode safe.

    All call sites construct this with precise Python types
    (``proc.pid`` is int, ``str(e)`` is str, ISO timestamps are str)
    and the persisted form is JSON which round-trips faithfully. Strict
    mode catches "wrong type slipped through" bugs early without
    introducing false positives from user-authored YAML coercion.
    """

    model_config = ConfigDict(
        extra="ignore",
        strict=True,
        validate_assignment=True,
    )

    spec_id: str
    status: str = "registered"
    pid: int | None = None
    port: int | None = None
    started_at: str | None = None
    last_health_check: str | None = None
    error_message: str | None = None
