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

    ``mode`` is the single source-of-truth axis: ``markdown`` (Markdown is the
    source, no graph), ``hybrid`` (Markdown is the source, a derived graph
    index powers the coverage / trace gates), or ``graph`` (the graph is the
    source, Markdown is an exported review view). ``kg_active_doc_types`` is the
    canonical set of doc_types whose context I/O routes through the graph.
    """

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    mode: str = "hybrid"
    kg_active_doc_types: list[str] = Field(default_factory=list)


class FrameworkProject(BaseModel):
    """Validated shape for the ``project`` section of ``framework.json``.

    ``languages`` is the project's declared language set (canonical ids from
    :mod:`cataforge.core.languages`); empty means "auto-detect from markers".
    ``design_tool`` gates the design integration (``none`` | ``penpot``); when
    ``penpot`` a ``.cataforge/mcp/penpot.yaml`` spec is present and `deploy`
    injects the Penpot MCP server into the platform config.
    """

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    languages: list[str] = Field(default_factory=list)
    design_tool: str = Field(default="none")


class FrameworkGitSessionSync(BaseModel):
    """Validated shape for ``git.session_sync`` — consumed by the SessionStart
    ``git_sync`` hook.

    ``enabled`` gates the whole hook. ``fast_forward_clean`` only fast-forwards
    when the session opened on the default branch with a clean tree.
    ``prune_gone`` deletes local branches whose upstream is gone (squash-merged).
    ``confirm_via_gh`` double-checks a merged PR before pruning. ``debounce_seconds``
    suppresses repeat fetches across rapid session restarts.
    """

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    enabled: bool = True
    fast_forward_clean: bool = True
    prune_gone: bool = True
    confirm_via_gh: bool = True
    debounce_seconds: int = 60
    fetch_timeout_seconds: int = 10


class FrameworkGitRemotePolicy(BaseModel):
    """Validated shape for ``git.remote_policy`` — the GitHub merge settings
    ``cataforge git ensure-policy`` (and bootstrap) keep idempotent."""

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    delete_branch_on_merge: bool = True
    squash_only: bool = True


class FrameworkGit(BaseModel):
    """Validated shape for the ``git`` section of ``framework.json``."""

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    session_sync: FrameworkGitSessionSync = Field(default_factory=FrameworkGitSessionSync)
    remote_policy: FrameworkGitRemotePolicy = Field(default_factory=FrameworkGitRemotePolicy)


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
    project: FrameworkProject = Field(default_factory=FrameworkProject)
    git: FrameworkGit = Field(default_factory=FrameworkGit)
