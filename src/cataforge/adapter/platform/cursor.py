"""Cursor platform adapter."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from cataforge.adapter.platform.adapter import PlatformAdapter
from cataforge.adapter.platform.fileops import symlink_or_copy
from cataforge.utils.atomic_write import atomic_write_text

if TYPE_CHECKING:
    from cataforge.runtime.deploy.manifest import DeployManifest as DeployManifest


class CursorAdapter(PlatformAdapter):
    @property
    def platform_id(self) -> str:
        return "cursor"

    @property
    def display_name(self) -> str:
        return "Cursor"

    def get_project_root_env_var(self) -> str | None:
        return "CURSOR_PROJECT_DIR"

    def get_agent_scan_dirs(self) -> list[str]:
        return list(self._profile.agent_definition.scan_dirs) or [".cursor/agents"]

    def get_agent_format(self) -> str:
        return "yaml-frontmatter"

    def deploy_additional_outputs_hook(
        self,
        rules_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: Any = None,
        prior_manifest: set[str] | None = None,
    ) -> list[str]:
        return self._generate_mdc_rules(rules_dir, project_root, dry_run=dry_run, manifest=manifest)

    def rules_target_relpath(self, platform_root: Path) -> str | None:
        # Cursor's canonical rule surface is ``.cursor/rules/*.mdc``, generated
        # by deploy_additional_outputs. Skip the base copy-render; the optional
        # ``.claude/rules`` mirror is handled by deploy_rules_extra.
        del platform_root
        return None

    def emit_extra_rules(
        self,
        source_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
        force_copy: bool = False,
    ) -> list[str]:
        """Optional ``.claude/rules`` Markdown mirror for cross-platform sharing.

        Off by default. Opt in via ``rules.cross_platform_mirror: true`` in
        ``.cataforge/platforms/cursor/profile.yaml`` — for projects that also
        run Claude Code against the same tree and want to share source-of-truth
        prompts.
        """
        if not self._profile.rules.cross_platform_mirror:
            if dry_run:
                return [
                    "SKIP: .claude/rules Markdown mirror "
                    "(enable via profile rules.cross_platform_mirror: true)"
                ]
            return []
        actions = symlink_or_copy(
            source_dir,
            project_root / ".claude" / "rules",
            dry_run=dry_run,
            force_copy=force_copy,
        )
        if manifest is not None and not dry_run:
            manifest.record(".claude/rules")
        note = (
            "note: Cursor deploy linked .claude/rules for cross-platform prompt "
            "sharing (profile rules.cross_platform_mirror=true)"
        )
        return actions + [note]

    def _generate_mdc_rules(
        self,
        source_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
    ) -> list[str]:
        """Generate .cursor/rules/ MDC files from canonical rule sources.

        Only handles ``.cataforge/rules/*.md`` here; override rules under
        ``.cataforge/platforms/cursor/overrides/rules/`` are picked up by
        the base-class ``deploy_overrides_rules`` flow which calls
        :meth:`wrap_rule_for_platform` (overridden below to produce the
        same MDC + ``alwaysApply`` wrapping).
        """
        output_dir = project_root / ".cursor" / "rules"
        if not dry_run:
            output_dir.mkdir(parents=True, exist_ok=True)

        actions: list[str] = []
        for md_file in sorted(source_dir.glob("*.md")):
            mdc_name = md_file.stem + ".mdc"
            mdc_rel = f".cursor/rules/{mdc_name}"
            if dry_run:
                actions.append(f"would deploy rules/{md_file.name} → .cursor/rules/{mdc_name}")
                continue
            content = md_file.read_text()
            mdc_content = _wrap_as_mdc(md_file.stem, content)
            atomic_write_text(output_dir / mdc_name, mdc_content)
            if manifest is not None:
                manifest.record(mdc_rel)
            actions.append(f"rules/{md_file.name} → .cursor/rules/{mdc_name}")

        return actions

    def wrap_rule_for_platform(self, name: str, content: str) -> tuple[str, str] | None:
        """Wrap an override rule as a Cursor MDC file with ``alwaysApply``.

        Called by the base-class ``deploy_overrides_rules`` flow for every
        ``.cataforge/platforms/cursor/overrides/rules/*.md`` file (including
        the auto-generated ``auto-*.md`` outputs from hook bridge
        ``apply_degradation``).
        """
        return (f".cursor/rules/{name}.mdc", _wrap_as_mdc(name, content))

    def mcp_json_path(self, project_root: Path) -> Path:
        return project_root / ".cursor" / "mcp.json"


def _wrap_as_mdc(name: str, content: str) -> str:
    """Wrap Markdown content with MDC frontmatter for Cursor."""
    frontmatter = f"""---
description: "{name} rules"
alwaysApply: true
---
"""
    return frontmatter + content
