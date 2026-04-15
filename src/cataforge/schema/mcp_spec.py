"""MCP server declarations (YAML / entry_points)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self


class HealthCheckSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["http", "tcp", "command"] = "http"
    target: str = ""
    interval_seconds: int = 30
    timeout_seconds: int = 5
    retries: int = 3


class MCPServerSpec(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

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
    model_config = ConfigDict(extra="ignore")

    spec_id: str
    status: str = "registered"
    pid: int | None = None
    port: int | None = None
    started_at: str | None = None
    last_health_check: str | None = None
    error_message: str | None = None
