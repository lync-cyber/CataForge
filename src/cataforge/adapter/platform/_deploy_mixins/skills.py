"""Skill-tree deployment mixin — thin delegate to the runtime step."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cataforge.runtime.deploy.manifest import DeployManifest as DeployManifest


class SkillDeployMixin:
    """Skill-tree deployment (per-skill dir → platform skill target)."""

    def deploy_skills(
        self,
        source_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        include_maintainer_only: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
        force_copy: bool = False,
    ) -> list[str]:
        from cataforge.runtime.deploy.steps import deploy_skills

        return deploy_skills(
            self,  # type: ignore[arg-type]
            source_dir,
            project_root,
            dry_run=dry_run,
            include_maintainer_only=include_maintainer_only,
            manifest=manifest,
            prior_manifest=prior_manifest,
            force_copy=force_copy,
        )
