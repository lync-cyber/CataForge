"""Codex CLI platform adapter."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from cataforge.adapter.platform.adapter import PlatformAdapter
from cataforge.adapter.platform.helpers import merge_codex_mcp_server

if TYPE_CHECKING:
    from cataforge.runtime.deploy.manifest import DeployManifest as DeployManifest


class CodexAdapter(PlatformAdapter):
    @property
    def platform_id(self) -> str:
        return "codex"

    @property
    def display_name(self) -> str:
        return "Codex CLI"

    def get_project_root_env_var(self) -> str | None:
        return "CODEX_HOME"

    def get_agent_scan_dirs(self) -> list[str]:
        return list(
            self._profile.get("agent_definition", {}).get("scan_dirs", [".codex/agents"])
        )

    def get_agent_format(self) -> str:
        return "toml"

    def deploy_agents(
        self,
        source_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
        prior_manifest: set[str] | None = None,
    ) -> list[str]:
        """Convert AGENT.md (YAML frontmatter) to TOML for Codex.

        The frontmatter is first run through the canonical
        :func:`translate_agent_md` pipeline (the shared
        ``_deploy_flat_agents`` helper does this) so capability
        translation, model tier resolution, and ``supported_fields``
        filtering happen exactly the same way as on every other
        platform — Codex just emits TOML instead of YAML, which the
        ``formatter`` argument plugs in. After deploy, orphan
        ``<name>.toml`` files whose source AGENT.md no longer exists are
        pruned via the helper's flat-prune pass with Codex's TOML head
        signature.
        """
        scan_dirs = self.get_agent_scan_dirs()
        if not scan_dirs:
            return []

        # Single source of truth for which extra fields survive into the TOML:
        # the profile's ``agent_config.supported_fields`` minus the keys the
        # formatter already emits explicitly (name/description). Adding a field
        # to the profile flows through here without a code change.
        passthrough = [
            f for f in self.agent_supported_fields if f not in _EXPLICIT_TOML_FIELDS
        ]

        def formatter(agent_id: str, content: str) -> str:
            return _md_to_toml(agent_id, content, passthrough)

        return self._deploy_flat_agents(
            source_dir,
            project_root,
            target_rel=scan_dirs[0],
            suffix=".toml",
            head_signature="# Auto-generated from {stem}/AGENT.md",
            head_read_size=256,
            formatter=formatter,
            dry_run=dry_run,
            manifest=manifest,
            prior_manifest=prior_manifest,
        )

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


# Fields the TOML formatter emits explicitly (under Codex-native names) and so
# excludes from the derived passthrough set.
_EXPLICIT_TOML_FIELDS = frozenset({"name", "description"})


def _md_to_toml(agent_id: str, content: str, passthrough: list[str]) -> str:
    """Convert AGENT.md (YAML frontmatter) to Codex TOML agent format.

    Uses ``yaml.safe_load`` for correct handling of lists, booleans,
    and nested values.  The output uses Codex's required field names:
    ``name``, ``description``, ``developer_instructions``.

    *passthrough* lists the additional frontmatter keys to copy through as-is
    (derived by the caller from the profile's supported_fields), preserving
    declaration order.
    """
    import re

    import yaml

    from cataforge.adapter.platform.helpers import _toml_value

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

    for key in passthrough:
        if key in data:
            lines.append(f"{key} = {_toml_value(data[key])}")

    return "\n".join(lines) + "\n"
