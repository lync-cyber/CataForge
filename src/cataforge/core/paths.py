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
    """Resolve a project root from a ``docs/`` directory, or ``None``.

    ``docs_dir`` is usually ``<root>/docs/`` (parent is the root); falls back
    to ``docs_dir`` itself when that is the root. Unlike :func:`find_project_root`
    this returns ``None`` (no cwd fallback) when no ``.cataforge/`` is found, so
    checkers can use it to decide whether the path is a CataForge project at all.
    """
    docs_path = Path(docs_dir).resolve()
    candidate = docs_path.parent
    if (candidate / ".cataforge").exists():
        return candidate
    if (docs_path / ".cataforge").exists():
        return docs_path
    return None


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
    def project_state_md(self) -> Path:
        return self.cataforge_dir / "PROJECT-STATE.md"

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
    def deploy_state(self) -> Path:
        return self.cataforge_dir / ".deploy-state"

    @property
    def deploy_manifest(self) -> Path:
        return self.root / DEPLOY_MANIFEST_REL

    @property
    def hook_error_log(self) -> Path:
        return self.root / HOOK_ERROR_LOG_REL

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

    # ---- helpers ----

    def platform_profile(self, platform_id: str) -> Path:
        return self.platforms_dir / platform_id / "profile.yaml"

    def platform_overrides(self, platform_id: str) -> Path:
        return self.platforms_dir / platform_id / "overrides"

    def skill_dir(self, skill_id: str) -> Path:
        return self.skills_dir / skill_id

    def agent_dir(self, agent_id: str) -> Path:
        return self.agents_dir / agent_id
