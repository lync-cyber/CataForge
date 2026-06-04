"""Agent deployment mixin — thin delegate to ``runtime.deploy.steps.agents``."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cataforge.runtime.deploy.manifest import DeployManifest as DeployManifest


class AgentDeployMixin:
    """Agent deployment (cataforge agents → platform-native agent files)."""

    def deploy_agents(
        self,
        source_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
    ) -> list[str]:
        from cataforge.runtime.deploy.steps import deploy_agents

        return deploy_agents(
            self,  # type: ignore[arg-type]
            source_dir,
            project_root,
            dry_run=dry_run,
            manifest=manifest,
            prior_manifest=prior_manifest,
        )
