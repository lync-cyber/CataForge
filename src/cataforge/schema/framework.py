"""Validated shape for ``.cataforge/framework.json``."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FrameworkRuntime(BaseModel):
    model_config = ConfigDict(extra="ignore")

    platform: str = "claude-code"


class FrameworkUpgradeSource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    repo: str | None = None


class FrameworkUpgrade(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: FrameworkUpgradeSource = Field(default_factory=FrameworkUpgradeSource)


class FrameworkFile(BaseModel):
    """Top-level framework.json — unknown keys preserved via ``extra='allow'``."""

    model_config = ConfigDict(extra="allow")

    version: str = "0.0.0"
    runtime: FrameworkRuntime | None = None
    constants: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)
    upgrade: FrameworkUpgrade | None = None
    migration_checks: list[Any] = Field(default_factory=list)
