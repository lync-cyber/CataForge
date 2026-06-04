"""Command + rules deployment mixin — thin delegate to the runtime step."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cataforge.runtime.deploy.manifest import DeployManifest as DeployManifest


class CommandRulesDeployMixin:
    """Command and rules deployment (+ overrides rules flow)."""

    def deploy_commands(
        self,
        source_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
    ) -> list[str]:
        from cataforge.runtime.deploy.steps import deploy_commands

        return deploy_commands(
            self,  # type: ignore[arg-type]
            source_dir,
            project_root,
            dry_run=dry_run,
            manifest=manifest,
            prior_manifest=prior_manifest,
        )

    def deploy_rules(
        self,
        source_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
        force_copy: bool = False,
    ) -> list[str]:
        from cataforge.runtime.deploy.steps import deploy_rules

        return deploy_rules(
            self,  # type: ignore[arg-type]
            source_dir,
            project_root,
            dry_run=dry_run,
            manifest=manifest,
            prior_manifest=prior_manifest,
            force_copy=force_copy,
        )

    def deploy_additional_outputs(
        self,
        rules_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
    ) -> list[str]:
        from cataforge.runtime.deploy.steps import deploy_additional_outputs

        return deploy_additional_outputs(
            self,  # type: ignore[arg-type]
            rules_dir,
            project_root,
            dry_run=dry_run,
            manifest=manifest,
            prior_manifest=prior_manifest,
        )

    def deploy_overrides_rules(
        self,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
    ) -> list[str]:
        from cataforge.runtime.deploy.steps import deploy_overrides_rules

        return deploy_overrides_rules(
            self,  # type: ignore[arg-type]
            project_root,
            dry_run=dry_run,
            manifest=manifest,
        )
