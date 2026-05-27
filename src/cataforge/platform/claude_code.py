"""Claude Code platform adapter."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from cataforge.platform.base import PlatformAdapter

if TYPE_CHECKING:
    from cataforge.deploy.manifest import DeployManifest as DeployManifest


class ClaudeCodeAdapter(PlatformAdapter):
    @property
    def platform_id(self) -> str:
        return "claude-code"

    @property
    def display_name(self) -> str:
        return "Claude Code"

    def get_project_root_env_var(self) -> str | None:
        return "CLAUDE_PROJECT_DIR"

    def get_agent_scan_dirs(self) -> list[str]:
        return list(self._profile.get("agent_definition", {}).get("scan_dirs", [".claude/agents"]))

    def get_agent_format(self) -> str:
        return "yaml-frontmatter"

    def deploy_agents(
        self,
        source_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
    ) -> list[str]:
        """Deploy agents using Claude Code's native ``<name>.md`` layout.

        Claude Code's documented sub-agent convention is a flat file per
        agent (``.claude/agents/<name>.md`` with YAML frontmatter).  The base
        implementation's ``<name>/AGENT.md`` subdir layout is not picked up
        by Claude Code's native ``/agents`` command, so we use the shared
        flat-layout helper to emit only the flat form, then layer on a
        pre-M? legacy-subdir cleanup specific to this adapter.

        Orphan pruning covers flat ``.md`` files we likely wrote and any
        leftover ``<name>/AGENT.md`` subdirs from prior deploys. The manifest
        scope adds a hard guard: even if a user-authored file matches our
        ``name: <stem>`` head signature by accident, prune still won't touch
        it unless we recorded the path in the previous deploy.
        """
        scan_dirs = self.get_agent_scan_dirs()
        if not scan_dirs:
            return []
        target_rel = scan_dirs[0]

        actions = self._deploy_flat_agents(
            source_dir,
            project_root,
            target_rel=target_rel,
            suffix=".md",
            head_signature="name: {stem}",
            formatter=lambda _name, translated: translated,
            dry_run=dry_run,
            manifest=manifest,
            prior_manifest=prior_manifest,
        )

        actions.extend(
            self._prune_legacy_agent_subdirs(
                project_root / target_rel,
                target_rel,
                prior_manifest=prior_manifest,
                dry_run=dry_run,
            )
        )
        return actions

    def _prune_legacy_agent_subdirs(
        self,
        target_dir: Path,
        target_rel: str,
        *,
        prior_manifest: set[str] | None,
        dry_run: bool,
    ) -> list[str]:
        """Tear down leftover ``<name>/AGENT.md`` subdirs from the pre-M?
        dual layout. Manifest-bounded so a user-authored agent subdir we
        never wrote stays put."""
        from cataforge.platform.helpers import remove_dir_with_manifest_check

        actions: list[str] = []
        if not target_dir.is_dir():
            return actions
        for existing in target_dir.iterdir():
            if not existing.is_dir() or not (existing / "AGENT.md").is_file():
                continue
            actions.extend(
                remove_dir_with_manifest_check(
                    existing,
                    display_rel=f"{target_rel}/{existing.name}",
                    manifest_key=f"{target_rel}/{existing.name}/AGENT.md",
                    prior_manifest=prior_manifest,
                    dry_run=dry_run,
                    kind="legacy",
                )
            )
        return actions

    def _mcp_json_path(self, project_root: Path) -> Path:
        return project_root / ".mcp.json"
