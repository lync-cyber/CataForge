"""Centralized path resolution — eliminates hardcoded paths.

Single source of truth for all framework directory/file paths.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("cataforge.paths")

# Project-relative locations (SSOT). CLI defaults, doctor gates, and the
# hook/deploy runtimes derive from these rather than re-spelling the literals.
KG_STORE_REL = Path(".cataforge") / "kg" / "store"
KG_SNAPSHOTS_REL = Path(".cataforge") / "kg" / "snapshots"
HOOK_ERROR_LOG_REL = Path(".cataforge") / ".hook-errors.jsonl"
DEPLOY_MANIFEST_REL = Path(".cataforge") / ".deploy-manifest.json"


def find_project_root_or_none(start: Path | None = None) -> Path | None:
    """Walk up from *start* (default: cwd) to the dir containing ``.cataforge/``.

    Returns ``None`` (no warning, no cwd fallback) when no ``.cataforge/``
    exists anywhere in the ancestor chain — callers that must not act outside a
    project (best-effort log writers, platform detection) branch on this.
    """
    d = (start or Path.cwd()).resolve()
    while True:
        if (d / ".cataforge").is_dir():
            return d
        parent = d.parent
        if parent == d:
            return None
        d = parent


def find_project_root(start: Path | None = None) -> Path:
    """Walk up from *start* (default: cwd) until a ``.cataforge/`` dir is found.

    Falls back to *cwd* with a warning if no ``.cataforge/`` directory exists
    anywhere in the ancestor chain.
    """
    root = find_project_root_or_none(start)
    if root is not None:
        return root
    cwd = Path.cwd().resolve()
    logger.warning(
        "No .cataforge/ directory found above %s; falling back to cwd (%s)",
        start or cwd,
        cwd,
    )
    return cwd


def project_root_from_env(start: Path | None = None) -> Path | None:
    """Resolve the active project root for builtin skill scripts.

    Prefers ``CATAFORGE_PROJECT_ROOT`` (injected by the skill runner so a
    subprocess scans the invoking project, not its own cwd). Falls back to
    an upward search from *start* / cwd, returning ``None`` when neither
    yields a project.
    """
    raw = os.environ.get("CATAFORGE_PROJECT_ROOT")
    if raw:
        return Path(raw)
    return find_project_root_or_none(start)


def project_root_from_docs_dir(docs_dir: Path | str) -> Path | None:
    """Resolve the enclosing project root from a docs directory, or ``None``.

    ``docs_dir`` may be the project ``docs/`` root, a doc_type subdir
    (``docs/arch/``), or the project root itself — the nearest ancestor
    containing ``.cataforge/`` is returned. Unlike :func:`find_project_root`
    this yields ``None`` (no cwd fallback) when no ``.cataforge/`` exists in the
    ancestor chain, so checkers can decide whether the path is a CataForge
    project at all.
    """
    return find_project_root_or_none(Path(docs_dir).resolve())


class ProjectPaths:
    """All well-known paths derived from a single project root."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or find_project_root()

    # ---- source (never platform-specific) ----

    @property
    def cataforge_dir(self) -> Path:
        return self.root / ".cataforge"

    @property
    def framework_json(self) -> Path:
        return self.cataforge_dir / "framework.json"

    @property
    def agents_dir(self) -> Path:
        return self.cataforge_dir / "agents"

    @property
    def skills_dir(self) -> Path:
        return self.cataforge_dir / "skills"

    @property
    def rules_dir(self) -> Path:
        return self.cataforge_dir / "rules"

    @property
    def hooks_dir(self) -> Path:
        return self.cataforge_dir / "hooks"

    @property
    def commands_dir(self) -> Path:
        return self.cataforge_dir / "commands"

    @property
    def scripts_dir(self) -> Path:
        return self.cataforge_dir / "scripts"

    @property
    def hooks_spec(self) -> Path:
        return self.hooks_dir / "hooks.yaml"

    @property
    def platforms_dir(self) -> Path:
        return self.cataforge_dir / "platforms"

    @property
    def schemas_dir(self) -> Path:
        return self.cataforge_dir / "schemas"

    @property
    def mcp_dir(self) -> Path:
        return self.cataforge_dir / "mcp"

    @property
    def plugins_dir(self) -> Path:
        return self.cataforge_dir / "plugins"

    @property
    def overrides_dir(self) -> Path:
        """Root of the user/project override layers.

        Lives outside the scaffold manifest, so ``upgrade apply`` never
        touches it — customisations here survive every framework refresh.
        """
        return self.cataforge_dir / "overrides"

    def override_layer(self, layer: str) -> Path:
        """Root of one override layer (``"project"`` or ``"user"``)."""
        return self.overrides_dir / layer

    @property
    def config_local_json(self) -> Path:
        """Machine-local config overlay (gitignored, whitelist fields only)."""
        return self.cataforge_dir / "config.local.json"

    # ---- run-state (gitignored, never in the shared config) ----

    @property
    def state_dir(self) -> Path:
        return self.cataforge_dir / "state"

    @property
    def locks_dir(self) -> Path:
        return self.state_dir / "locks"

    @property
    def config_lock(self) -> Path:
        return self.locks_dir / "config.lock"

    @property
    def deploy_lock(self) -> Path:
        return self.locks_dir / "deploy.lock"

    @property
    def upgrade_state(self) -> Path:
        return self.state_dir / "upgrade.json"

    @property
    def deploy_state_root(self) -> Path:
        """Per-platform deploy state root: ``state/deploy/<platform>/``."""
        return self.state_dir / "deploy"

    def platform_deploy_dir(self, platform_id: str) -> Path:
        return self.deploy_state_root / platform_id

    def platform_deploy_state(self, platform_id: str) -> Path:
        return self.platform_deploy_dir(platform_id) / "state.json"

    def platform_deploy_manifest(self, platform_id: str) -> Path:
        return self.platform_deploy_dir(platform_id) / "manifest.json"

    # ---- legacy single-slot deploy records (read-compat + migration source) ----

    @property
    def deploy_state(self) -> Path:
        return self.cataforge_dir / ".deploy-state"

    @property
    def deploy_manifest(self) -> Path:
        return self.root / DEPLOY_MANIFEST_REL

    @property
    def hook_error_log(self) -> Path:
        return self.root / HOOK_ERROR_LOG_REL

    @property
    def git_sync_stamp(self) -> Path:
        """Debounce marker for the SessionStart ``git_sync`` hook (gitignored)."""
        return self.cataforge_dir / ".git-sync-stamp"

    @property
    def docs_dir(self) -> Path:
        return self.root / "docs"

    @property
    def event_log(self) -> Path:
        from cataforge.core.event_log import EVENT_LOG_REL

        return self.root / EVENT_LOG_REL

    @property
    def mcp_state_dir(self) -> Path:
        return self.cataforge_dir / ".mcp-state"

    @property
    def kg_store_dir(self) -> Path:
        return self.root / KG_STORE_REL

    @property
    def kg_snapshots_dir(self) -> Path:
        return self.root / KG_SNAPSHOTS_REL

    # ---- helpers ----

    def platform_profile(self, platform_id: str) -> Path:
        return self.platforms_dir / platform_id / "profile.yaml"

    def platform_overrides(self, platform_id: str) -> Path:
        return self.platforms_dir / platform_id / "overrides"

    def skill_dir(self, skill_id: str) -> Path:
        return self.skills_dir / skill_id

    def agent_dir(self, agent_id: str) -> Path:
        return self.agents_dir / agent_id
