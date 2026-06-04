"""Instruction-file deployment mixin — thin delegate to the runtime step."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cataforge.runtime.deploy.manifest import DeployManifest as DeployManifest


class InstructionDeployMixin:
    """Instruction-file deployment (CLAUDE.md / AGENTS.md + extras)."""

    def deploy_instruction_files(
        self,
        project_state_path: Path,
        project_root: Path,
        *,
        platform_id: str,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
    ) -> list[str]:
        from cataforge.runtime.deploy.steps import deploy_instruction_files

        return deploy_instruction_files(
            self,  # type: ignore[arg-type]
            project_state_path,
            project_root,
            platform_id=platform_id,
            dry_run=dry_run,
            manifest=manifest,
            prior_manifest=prior_manifest,
        )
