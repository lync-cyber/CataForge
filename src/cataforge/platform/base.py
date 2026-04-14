"""PlatformAdapter abstract base class.

All platform-specific differences are encapsulated here.
The core runtime NEVER imports platform-specific modules directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class PlatformAdapter(ABC):
    """Abstract base for all AI IDE platform adapters."""

    def __init__(self, profile: dict[str, Any]) -> None:
        self._profile = profile

    # ---- identity ----

    @property
    @abstractmethod
    def platform_id(self) -> str: ...

    @property
    @abstractmethod
    def display_name(self) -> str: ...

    # ---- tool mapping ----

    @abstractmethod
    def get_tool_map(self) -> dict[str, str | None]:
        """Return capability_id → native_tool_name mapping (core 10)."""
        ...

    def get_extended_tool_map(self) -> dict[str, str | None]:
        """Return extended capability → native tool name mapping.

        Extended capabilities (notebook_edit, browser_preview, etc.) are
        declared in ``profile.yaml`` under ``extended_capabilities``.
        """
        return dict(self._profile.get("extended_capabilities", {}))

    def get_full_tool_map(self) -> dict[str, str | None]:
        """Return combined core + extended capability mapping."""
        combined = self.get_tool_map()
        combined.update(self.get_extended_tool_map())
        return combined

    def resolve_tool_name(self, capability: str) -> str | None:
        return self.get_full_tool_map().get(capability)

    def resolve_tools_list(self, capabilities: list[str]) -> list[str]:
        tool_map = self.get_full_tool_map()
        return [name for cap in capabilities if (name := tool_map.get(cap)) is not None]

    # ---- project root ----

    @abstractmethod
    def get_project_root_env_var(self) -> str | None:
        """Return the environment variable name for project root (e.g. CLAUDE_PROJECT_DIR)."""
        ...

    def get_hook_command_template(self) -> str:
        """Return the hook command template with {module} placeholder.

        Hooks are invoked via ``python -m cataforge.hook.scripts.<module>``.
        """
        return "python -m cataforge.hook.scripts.{module}"

    # ---- agent deployment ----

    @abstractmethod
    def get_agent_scan_dirs(self) -> list[str]:
        """Return directories the IDE scans for agent definitions."""
        ...

    @abstractmethod
    def get_agent_format(self) -> str:
        """Return agent definition format: 'yaml-frontmatter' or 'toml'."""
        ...

    @property
    def needs_agent_deploy(self) -> bool:
        return bool(self._profile.get("agent_definition", {}).get("needs_deploy", True))

    def deploy_agents(
        self, source_dir: Path, project_root: Path, *, dry_run: bool = False
    ) -> list[str]:
        """Deploy agent definitions to platform target directories.

        Default: translates yaml-frontmatter agent files and copies them.
        Subclasses override for different formats (e.g. TOML).
        """
        from cataforge.agent.translator import translate_agent_md

        scan_dirs = self.get_agent_scan_dirs()
        if not scan_dirs:
            return []

        target_dir = project_root / scan_dirs[0]
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        actions: list[str] = []
        if not source_dir.is_dir():
            return actions

        for agent_name in sorted(d.name for d in source_dir.iterdir() if d.is_dir()):
            agent_src = source_dir / agent_name
            agent_dst = target_dir / agent_name
            if dry_run:
                for md_file in sorted(agent_src.glob("*.md")):
                    actions.append(
                        f"would deploy agents/{agent_name}/{md_file.name} → "
                        f"{scan_dirs[0]}/{md_file.name}"
                    )
                continue

            agent_dst.mkdir(exist_ok=True)

            for md_file in sorted(agent_src.glob("*.md")):
                content = md_file.read_text(encoding="utf-8")
                translated = translate_agent_md(content, self)
                (agent_dst / md_file.name).write_text(translated, encoding="utf-8")
                actions.append(f"agents/{agent_name}/{md_file.name} → {scan_dirs[0]}")

        return actions

    # ---- instruction file ----

    @property
    def reads_claude_md(self) -> bool:
        return bool(self._profile.get("instruction_file", {}).get("reads_claude_md", False))

    @property
    def additional_outputs(self) -> list[dict[str, Any]]:
        return list(self._profile.get("instruction_file", {}).get("additional_outputs", []))

    @property
    def instruction_targets(self) -> list[dict[str, Any]]:
        """Instruction artifacts this platform expects.

        Each entry uses:
        - ``type``: currently ``project_state_copy``
        - ``path``: relative output path (for example ``CLAUDE.md`` / ``AGENTS.md``)
        """
        targets = self._profile.get("instruction_file", {}).get("targets")
        if isinstance(targets, list) and targets:
            return [dict(t) for t in targets if isinstance(t, dict)]
        if self.reads_claude_md:
            return [{"type": "project_state_copy", "path": "CLAUDE.md"}]
        return []

    def deploy_instruction_files(
        self,
        project_state_path: Path,
        project_root: Path,
        *,
        platform_id: str,
        dry_run: bool = False,
    ) -> list[str]:
        """Deploy platform instruction artifacts derived from PROJECT-STATE.md."""
        if not project_state_path.is_file():
            return ["SKIP: PROJECT-STATE.md not found"]

        content = project_state_path.read_text(encoding="utf-8")
        content = content.replace("运行时: {platform}", f"运行时: {platform_id}")
        actions: list[str] = []

        for target in self.instruction_targets:
            target_type = str(target.get("type", ""))
            target_rel = str(target.get("path", ""))
            if not target_rel:
                continue
            if target_type != "project_state_copy":
                actions.append(f"SKIP: unsupported instruction target type {target_type}")
                continue

            dst = project_root / target_rel
            if dry_run:
                actions.append(
                    f"would write {target_rel} ← PROJECT-STATE.md (platform={platform_id})"
                )
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(content, encoding="utf-8")
            actions.append(f"{target_rel} ← PROJECT-STATE.md (platform={platform_id})")

        return actions

    # ---- dispatch ----

    @property
    def dispatch_info(self) -> dict[str, Any]:
        return dict(self._profile.get("dispatch", {}))

    # ---- hooks ----

    @property
    def hook_config_format(self) -> str | None:
        return self._profile.get("hooks", {}).get("config_format")

    @property
    def hook_config_path(self) -> str | None:
        return self._profile.get("hooks", {}).get("config_path")

    @property
    def hook_event_map(self) -> dict[str, str | None]:
        return dict(self._profile.get("hooks", {}).get("event_map", {}))

    @property
    def hook_degradation(self) -> dict[str, str]:
        return dict(self._profile.get("hooks", {}).get("degradation", {}))

    @property
    def hook_tool_overrides(self) -> dict[str, str]:
        """Per-platform overrides for hook matcher tool names.

        Hook matchers may use different names from the tool_map (e.g. Codex
        tool_map has ``shell_exec: shell`` but hook events use ``Bash``).
        When present, these override tool_map for hook matcher resolution only.
        """
        return dict(self._profile.get("hooks", {}).get("tool_overrides", {}))

    # ---- rules deployment ----

    def deploy_rules(
        self, source_dir: Path, project_root: Path, *, dry_run: bool = False
    ) -> list[str]:
        """Deploy rule files to the platform's rule directory.

        Default: symlink/copy to ``<scan_dirs[0]>/../rules``.
        Subclasses override for additional outputs (e.g. Cursor MDC).
        """
        from cataforge.platform.helpers import symlink_or_copy

        scan_dirs = self.get_agent_scan_dirs()
        if not scan_dirs:
            return []
        platform_root = Path(scan_dirs[0]).parent
        target = project_root / platform_root / "rules"
        return symlink_or_copy(source_dir, target, dry_run=dry_run)

    # ---- additional outputs ----

    def deploy_additional_outputs(
        self, rules_dir: Path, project_root: Path, *, dry_run: bool = False
    ) -> list[str]:
        """Deploy platform-specific additional outputs.

        Default: no-op. Subclasses override (e.g. Cursor MDC rules).
        """
        return []

    # ---- agent configuration ----

    @property
    def agent_supported_fields(self) -> list[str]:
        """Agent frontmatter fields this platform supports.

        Declared in ``profile.yaml`` under ``agent_config.supported_fields``.
        Used by the translator/deployer to decide which fields to pass through.
        """
        return list(self._profile.get("agent_config", {}).get("supported_fields", []))

    @property
    def agent_memory_scopes(self) -> list[str]:
        """Memory scopes the platform supports for agent-level persistence.

        Typical values: ``user``, ``project``, ``local``.
        """
        return list(self._profile.get("agent_config", {}).get("memory_scopes", []))

    @property
    def agent_isolation_modes(self) -> list[str]:
        """Isolation modes the platform supports (e.g. ``worktree``)."""
        return list(self._profile.get("agent_config", {}).get("isolation_modes", []))

    # ---- platform features ----

    def get_supported_features(self) -> dict[str, bool]:
        """Return platform feature flags.

        Declared in ``profile.yaml`` under ``features``.  These describe
        higher-order platform behaviors (cloud agents, agent teams, etc.),
        not per-tool mappings.
        """
        return dict(self._profile.get("features", {}))

    def supports_feature(self, feature: str) -> bool:
        """Check whether a specific feature is supported."""
        return bool(self._profile.get("features", {}).get(feature, False))

    # ---- permissions ----

    @property
    def permission_modes(self) -> list[str]:
        """Permission/approval modes this platform supports.

        Declared in ``profile.yaml`` under ``permissions.modes``.
        """
        return list(self._profile.get("permissions", {}).get("modes", []))

    # ---- model routing ----

    @property
    def available_models(self) -> list[str]:
        """Models available on this platform for selection."""
        return list(self._profile.get("model_routing", {}).get("available_models", []))

    @property
    def supports_per_agent_model(self) -> bool:
        """Whether the platform supports per-agent model selection."""
        return bool(self._profile.get("model_routing", {}).get("per_agent_model", False))

    # ---- MCP ----

    @abstractmethod
    def inject_mcp_config(
        self,
        server_id: str,
        server_config: dict[str, Any],
        project_root: Path,
        *,
        dry_run: bool = False,
    ) -> list[str]:
        """Write MCP server config into the platform's configuration file."""
        ...
