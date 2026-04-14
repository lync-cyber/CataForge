"""OpenCode platform adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cataforge.agent.translator import translate_agent_md
from cataforge.platform.base import PlatformAdapter
from cataforge.platform.helpers import merge_json_key, merge_opencode_project_mcp


class OpenCodeAdapter(PlatformAdapter):
    @property
    def platform_id(self) -> str:
        return "opencode"

    @property
    def display_name(self) -> str:
        return "OpenCode"

    def get_tool_map(self) -> dict[str, str | None]:
        return dict(self._profile.get("tool_map", {}))

    def get_project_root_env_var(self) -> str | None:
        return None

    def get_agent_scan_dirs(self) -> list[str]:
        return list(
            self._profile.get("agent_definition", {}).get("scan_dirs", [".claude/agents"])
        )

    def get_agent_format(self) -> str:
        return "yaml-frontmatter"

    def deploy_agents(
        self, source_dir: Path, project_root: Path, *, dry_run: bool = False
    ) -> list[str]:
        """Deploy AGENT.md files to OpenCode native ``.opencode/agents/*.md``."""
        target_dir = project_root / ".opencode" / "agents"
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        actions: list[str] = []
        if not source_dir.is_dir():
            return actions

        for agent_dir in sorted(source_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            agent_md = agent_dir / "AGENT.md"
            if not agent_md.is_file():
                continue
            target_file = target_dir / f"{agent_dir.name}.md"
            if dry_run:
                actions.append(
                    f"would deploy agents/{agent_dir.name}/AGENT.md → .opencode/agents/{agent_dir.name}.md"
                )
                continue
            content = agent_md.read_text(encoding="utf-8")
            translated = translate_agent_md(content, self)
            target_file.write_text(translated, encoding="utf-8")
            actions.append(
                f"agents/{agent_dir.name}/AGENT.md → .opencode/agents/{agent_dir.name}.md"
            )

        return actions

    def deploy_instruction_files(
        self,
        project_state_path: Path,
        project_root: Path,
        *,
        platform_id: str,
        dry_run: bool = False,
    ) -> list[str]:
        actions = super().deploy_instruction_files(
            project_state_path, project_root, platform_id=platform_id, dry_run=dry_run
        )
        actions.extend(
            merge_json_key(
                project_root / "opencode.json",
                "instructions",
                ["AGENTS.md", ".cataforge/rules/*.md"],
                dry_run=dry_run,
            )
        )
        return actions

    def inject_mcp_config(
        self,
        server_id: str,
        server_config: dict[str, Any],
        project_root: Path,
        *,
        dry_run: bool = False,
    ) -> list[str]:
        return merge_opencode_project_mcp(
            project_root, server_id, server_config, dry_run=dry_run
        )
