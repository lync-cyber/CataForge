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


class FrameworkKG(BaseModel):
    """Validated shape for the ``kg`` section of ``framework.json``.

    Store-level connection settings only; the active doc_type set lives
    on :class:`FrameworkContext`.
    """

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    project_id: str = "proj-default"
    title: str = "(unnamed)"
    process_model: str = "waterfall"


class FrameworkContext(BaseModel):
    """Validated shape for the ``context`` section of ``framework.json``.

    ``strategy`` selects the context-IO backend topology: ``kg-first``
    (graph is the source-of-truth, Markdown is the exported review view)
    or ``doc-only`` (Markdown is the source, no graph backend).
    ``kg_active_doc_types`` is the canonical set of doc_types whose
    context I/O routes through the graph.
    """

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    strategy: str = "kg-first"
    kg_active_doc_types: list[str] = Field(default_factory=list)


class FrameworkFile(BaseModel):
    """Top-level framework.json — unknown keys preserved via ``extra='allow'``."""

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    version: str = "0.0.0"
    runtime: FrameworkRuntime | None = None
    constants: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)
    upgrade: FrameworkUpgrade | None = None
    migration_checks: list[Any] = Field(default_factory=list)
    kg: FrameworkKG = Field(default_factory=FrameworkKG)
    context: FrameworkContext = Field(default_factory=FrameworkContext)
