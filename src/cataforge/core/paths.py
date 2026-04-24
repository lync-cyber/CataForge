"""Centralized path resolution — eliminates hardcoded paths.

Single source of truth for all framework directory/file paths.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("cataforge.paths")


def find_project_root(start: Path | None = None) -> Path:
    """Walk up from *start* (default: cwd) until a ``.cataforge/`` dir is found.

    Falls back to *cwd* with a warning if no ``.cataforge/`` directory exists
    anywhere in the ancestor chain.
    """
    d = (start or Path.cwd()).resolve()
    while True:
        if (d / ".cataforge").is_dir():
            return d
        parent = d.parent
        if parent == d:
            cwd = Path.cwd().resolve()
            logger.warning(
                "No .cataforge/ directory found above %s; falling back to cwd (%s)",
                start or cwd,
                cwd,
            )
            return cwd
        d = parent


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
    def event_log(self) -> Path:
        from cataforge.core.event_log import EVENT_LOG_REL
        return self.root / EVENT_LOG_REL

    @property
    def mcp_state_dir(self) -> Path:
        return self.cataforge_dir / ".mcp-state"

    # ---- helpers ----

    def platform_profile(self, platform_id: str) -> Path:
        return self.platforms_dir / platform_id / "profile.yaml"

    def platform_overrides(self, platform_id: str) -> Path:
        return self.platforms_dir / platform_id / "overrides"

    def skill_dir(self, skill_id: str) -> Path:
        return self.skills_dir / skill_id

    def agent_dir(self, agent_id: str) -> Path:
        return self.agents_dir / agent_id
