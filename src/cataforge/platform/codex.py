"""Codex CLI platform adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cataforge.platform.base import PlatformAdapter
from cataforge.platform.helpers import merge_codex_mcp_server


class CodexAdapter(PlatformAdapter):
    @property
    def platform_id(self) -> str:
        return "codex"

    @property
    def display_name(self) -> str:
        return "Codex CLI"

    def get_tool_map(self) -> dict[str, str | None]:
        return dict(self._profile.get("tool_map", {}))

    def get_project_root_env_var(self) -> str | None:
        return "CODEX_HOME"

    def get_agent_scan_dirs(self) -> list[str]:
        return list(
            self._profile.get("agent_definition", {}).get("scan_dirs", [".codex/agents"])
        )

    def get_agent_format(self) -> str:
        return "toml"

    def deploy_agents(
        self, source_dir: Path, project_root: Path, *, dry_run: bool = False
    ) -> list[str]:
        """Convert AGENT.md (YAML frontmatter) to TOML for Codex."""
        scan_dirs = self.get_agent_scan_dirs()
        if not scan_dirs:
            return []

        target_dir = project_root / scan_dirs[0]
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

            toml_path = target_dir / f"{agent_dir.name}.toml"
            if dry_run:
                actions.append(f"would deploy agents/{agent_dir.name}/AGENT.md → {toml_path}")
                continue

            content = agent_md.read_text(encoding="utf-8")
            toml_content = _md_to_toml(agent_dir.name, content)
            toml_path.write_text(toml_content, encoding="utf-8")
            actions.append(f"agents/{agent_dir.name}/AGENT.md → {toml_path}")

        return actions

    def inject_mcp_config(
        self,
        server_id: str,
        server_config: dict[str, Any],
        project_root: Path,
        *,
        dry_run: bool = False,
    ) -> list[str]:
        config_path = project_root / ".codex" / "config.toml"
        return merge_codex_mcp_server(
            config_path, server_id, server_config, dry_run=dry_run
        )


def _md_to_toml(agent_id: str, content: str) -> str:
    """Convert AGENT.md (YAML frontmatter) to Codex TOML agent format.

    Uses ``yaml.safe_load`` for correct handling of lists, booleans,
    and nested values.  The output uses Codex's required field names:
    ``name``, ``description``, ``developer_instructions``.
    """
    import re

    import yaml

    from cataforge.platform.helpers import _toml_value

    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
    if not fm_match:
        raise ValueError(f"Cannot parse YAML frontmatter in {agent_id}/AGENT.md")

    data = yaml.safe_load(fm_match.group(1)) or {}
    body = fm_match.group(2).strip()

    lines = [f"# Auto-generated from {agent_id}/AGENT.md"]
    lines.append(f'name = {_toml_value(data.get("name", agent_id))}')

    if "description" in data:
        lines.append(f'description = {_toml_value(data["description"])}')

    # Codex uses developer_instructions (not instructions)
    lines.append("")
    lines.append(f'developer_instructions = """\n{body}\n"""')

    # Pass through optional Codex-recognized fields
    for key in ("model", "model_reasoning_effort", "sandbox_mode", "nickname_candidates"):
        if key in data:
            lines.append(f"{key} = {_toml_value(data[key])}")

    return "\n".join(lines) + "\n"
