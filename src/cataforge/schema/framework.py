"""Validated shape for ``.cataforge/framework.json``.

All nested models use ``extra='allow'`` so user-authored fields (e.g.
``upgrade.source.branch`` / ``upgrade.source.token_env`` / ``upgrade.state.*``)
survive a Pydantic validate → dump round-trip intact.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FrameworkRuntime(BaseModel):
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    platform: str = "claude-code"


class FrameworkUpgradeSource(BaseModel):
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    repo: str | None = None


class FrameworkUpgrade(BaseModel):
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    source: FrameworkUpgradeSource = Field(default_factory=FrameworkUpgradeSource)


class FrameworkFile(BaseModel):
    """Top-level framework.json — unknown keys preserved via ``extra='allow'``."""

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    version: str = "0.0.0"
    runtime: FrameworkRuntime | None = None
    constants: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)
    upgrade: FrameworkUpgrade | None = None
    migration_checks: list[Any] = Field(default_factory=list)
