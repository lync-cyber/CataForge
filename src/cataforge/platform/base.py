"""PlatformAdapter abstract base class.

All platform-specific differences are encapsulated here.
The core runtime NEVER imports platform-specific modules directly.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from cataforge.platform.section_merge import merge_sections

_INSTRUCTION_HASHES_REL = ".cataforge/.instruction-hashes.json"
_VALID_ON_CONFLICT = {"overwrite", "preserve", "preserve_if_edited"}
_VALID_UPDATE_STRATEGY = {"overwrite", "section-merge"}


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

    def get_tool_map(self) -> dict[str, str | None]:
        """Return capability_id → native_tool_name mapping (core 10).

        Default: read ``tool_map`` from the platform profile.  Subclasses
        override only when they need to synthesize the mapping differently.
        """
        return dict(self._profile.get("tool_map", {}))

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
        target_rel = scan_dirs[0]
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        actions: list[str] = []
        if not source_dir.is_dir():
            return actions

        source_agents = {
            d.name
            for d in source_dir.iterdir()
            if d.is_dir() and (d / "AGENT.md").is_file()
        }

        # Collect dropped capabilities across all agents so we emit ONE line
        # per platform instead of spamming one warning per agent per field.
        dropped_collector: dict[str, set[str]] = {}

        # Only AGENT.md is an IDE-visible agent definition. Sibling files
        # (e.g. ORCHESTRATOR-PROTOCOLS.md) are reference material for the
        # agent itself — they live in .cataforge/ and are read by the agent
        # at runtime, not registered as additional agents.
        for agent_name in sorted(source_agents):
            agent_md = source_dir / agent_name / "AGENT.md"
            agent_dst = target_dir / agent_name
            if dry_run:
                # Show both the logical source and the physical target so users
                # can't confuse "same filename in every line" for "all agents
                # being written to the same file".
                actions.append(
                    f"would deploy agent {agent_name:<24} "
                    f"→ {target_rel}/{agent_name}/AGENT.md"
                )
                continue

            agent_dst.mkdir(exist_ok=True)
            content = agent_md.read_text(encoding="utf-8")
            translated = translate_agent_md(
                content, self, dropped_collector=dropped_collector
            )
            (agent_dst / "AGENT.md").write_text(translated, encoding="utf-8")
            actions.append(f"agents/{agent_name}/AGENT.md → {target_rel}")

            # Prune stale sibling files inside this agent subdir — they were
            # historically deployed (e.g. ORCHESTRATOR-PROTOCOLS.md) but are
            # no longer part of the IDE-visible surface.
            for stale in agent_dst.iterdir():
                if stale.is_file() and stale.name != "AGENT.md":
                    stale.unlink()
                    actions.append(f"pruned stale {target_rel}/{agent_name}/{stale.name}")

        # Emit a single aggregated WARN per field, listing every dropped cap.
        for field_name in sorted(dropped_collector):
            caps = sorted(dropped_collector[field_name])
            actions.append(
                f"WARN: {self.platform_id}: {len(caps)} capability id(s) in "
                f"{field_name!r} have no platform mapping: {caps} — "
                "these will be skipped during translation."
            )

        # Prune orphan agent subdirs that no longer exist in source. We only
        # remove dirs that look like ours (have AGENT.md) so we never touch
        # IDE-native or user-authored agents living alongside.
        if target_dir.is_dir():
            for existing in target_dir.iterdir():
                if (
                    not existing.is_dir()
                    or existing.name in source_agents
                    or not (existing / "AGENT.md").is_file()
                ):
                    continue
                if dry_run:
                    actions.append(f"would prune orphan {scan_dirs[0]}/{existing.name}/")
                else:
                    import shutil as _shutil

                    _shutil.rmtree(existing)
                    actions.append(f"pruned orphan {scan_dirs[0]}/{existing.name}/")

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
        """Deploy platform instruction artifacts derived from PROJECT-STATE.md.

        Each target entry may declare:
        - ``on_conflict``: ``overwrite`` (default) | ``preserve`` |
          ``preserve_if_edited``.  ``preserve_if_edited`` skips write when the
          target's sha256 differs from the hash recorded at last deploy.
        - ``update_strategy``: ``overwrite`` (default) | ``section-merge``.
          ``section-merge`` preserves user-added sections and field values per
          the ``section_policy`` declared on the target.
        """
        if not project_state_path.is_file():
            return ["SKIP: PROJECT-STATE.md not found"]

        content = project_state_path.read_text(encoding="utf-8")
        content = content.replace("运行时: {platform}", f"运行时: {platform_id}")

        # Prepend an at-mention preamble when the platform declares one via
        # context_injection.  Today only Claude Code uses this — CLAUDE.md gets
        # `@.cataforge/rules/COMMON-RULES.md` at the top so the shared rule
        # file rides into every session without a runtime Read call.
        preamble = self.get_instruction_preamble()
        if preamble:
            content = preamble + content

        actions: list[str] = []
        hashes = _load_instruction_hashes(project_root)
        hashes_dirty = False

        for target in self.instruction_targets:
            target_type = str(target.get("type", ""))
            target_rel = str(target.get("path", ""))
            if not target_rel:
                continue
            if target_type != "project_state_copy":
                actions.append(f"SKIP: unsupported instruction target type {target_type}")
                continue

            on_conflict = str(target.get("on_conflict", "overwrite"))
            if on_conflict not in _VALID_ON_CONFLICT:
                actions.append(
                    f"SKIP {target_rel}: invalid on_conflict={on_conflict!r} "
                    f"(must be one of {sorted(_VALID_ON_CONFLICT)})"
                )
                continue

            update_strategy = str(target.get("update_strategy", "overwrite"))
            if update_strategy not in _VALID_UPDATE_STRATEGY:
                actions.append(
                    f"SKIP {target_rel}: invalid update_strategy={update_strategy!r} "
                    f"(must be one of {sorted(_VALID_UPDATE_STRATEGY)})"
                )
                continue

            dst = project_root / target_rel

            # ---- on_conflict gate ----
            if dst.exists() and on_conflict != "overwrite":
                if on_conflict == "preserve":
                    actions.append(
                        f"SKIP {target_rel} ← on_conflict=preserve (target exists)"
                    )
                    continue
                # preserve_if_edited: compare sha256 with last-deployed hash
                cur_hash = hashlib.sha256(dst.read_bytes()).hexdigest()
                last_hash = hashes.get(target_rel)
                if last_hash is not None and cur_hash != last_hash:
                    actions.append(
                        f"SKIP {target_rel} ← on_conflict=preserve_if_edited "
                        f"(user-edited since last deploy)"
                    )
                    continue

            # ---- compute new content ----
            new_content = content
            if update_strategy == "section-merge" and dst.exists():
                section_policy = target.get("section_policy", {}) or {}
                current_text = dst.read_text(encoding="utf-8")
                new_content = merge_sections(
                    current_text,
                    content,
                    policy=section_policy,
                    platform_id=platform_id,
                )

            if dry_run:
                actions.append(
                    f"would write {target_rel} ← PROJECT-STATE.md "
                    f"(platform={platform_id}, strategy={update_strategy}, "
                    f"on_conflict={on_conflict})"
                )
                continue

            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(new_content, encoding="utf-8")
            # Hash what's actually on disk — avoids Windows CRLF translation
            # making cur_hash on subsequent deploys diverge from the stored
            # hash even when the user has not edited the file.
            hashes[target_rel] = hashlib.sha256(dst.read_bytes()).hexdigest()
            hashes_dirty = True
            actions.append(
                f"{target_rel} ← PROJECT-STATE.md (platform={platform_id}, "
                f"strategy={update_strategy})"
            )

        if hashes_dirty and not dry_run:
            _save_instruction_hashes(project_root, hashes)

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

    @property
    def hook_entry_type(self) -> str | None:
        """Platform-native value for a hook entry's ``type`` field.

        Declared in ``profile.yaml`` under ``hooks.entry_type`` (e.g. Claude
        Code, Cursor and Codex all use ``"command"``).  When ``None`` the
        bridge falls back to the internal ``type`` from ``hooks.yaml`` — used
        only by platforms that do not emit JSON hook configs (e.g. OpenCode
        which uses plugins).
        """
        value = self._profile.get("hooks", {}).get("entry_type")
        return str(value) if value else None

    # ---- skills deployment ----

    @property
    def needs_skill_deploy(self) -> bool:
        """Whether this platform wants skill definitions deployed to an IDE-visible path."""
        return bool(self._profile.get("skill_definition", {}).get("needs_deploy", False))

    def get_skill_target_dir(self) -> str | None:
        """Target directory (relative to project root) for IDE-visible skills."""
        target = self._profile.get("skill_definition", {}).get("target_dir")
        return str(target) if target else None

    def deploy_skills(
        self, source_dir: Path, project_root: Path, *, dry_run: bool = False
    ) -> list[str]:
        """Expose skills to the IDE via symlink/junction/copy, like rules.

        Default: link ``<target_dir>`` → ``.cataforge/skills``.  Subclasses can
        override to transform content per platform.
        """
        from cataforge.platform.helpers import symlink_or_copy

        target_rel = self.get_skill_target_dir()
        if not target_rel or not source_dir.is_dir():
            return []
        target = project_root / target_rel
        return symlink_or_copy(source_dir, target, dry_run=dry_run)

    # ---- slash commands deployment ----

    @property
    def needs_command_deploy(self) -> bool:
        """Whether this platform has a slash-command surface to deploy to."""
        return bool(self._profile.get("command_definition", {}).get("needs_deploy", False))

    def get_command_target_dir(self) -> str | None:
        """Target directory (relative to project root) for IDE-visible slash commands."""
        target = self._profile.get("command_definition", {}).get("target_dir")
        return str(target) if target else None

    def deploy_commands(
        self, source_dir: Path, project_root: Path, *, dry_run: bool = False
    ) -> list[str]:
        """Copy ``.cataforge/commands/*.md`` into the platform's slash-command dir.

        Default: flat copy of every ``*.md`` file.  Subclasses may override for
        platforms with different slash-command formats.
        """
        target_rel = self.get_command_target_dir()
        if not target_rel or not source_dir.is_dir():
            return []
        target_dir = project_root / target_rel
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        source_names = {md.name for md in source_dir.glob("*.md")}
        actions: list[str] = []

        # Prune stale commands that were deployed previously but removed / renamed
        # upstream. Only touch *.md files — never delete IDE-native artifacts.
        if target_dir.is_dir():
            for existing in target_dir.glob("*.md"):
                if existing.name in source_names:
                    continue
                if dry_run:
                    actions.append(f"would prune orphan {target_rel}/{existing.name}")
                else:
                    existing.unlink()
                    actions.append(f"pruned orphan {target_rel}/{existing.name}")

        for md_file in sorted(source_dir.glob("*.md")):
            dst = target_dir / md_file.name
            if dry_run:
                actions.append(
                    f"would deploy commands/{md_file.name} → "
                    f"{target_rel}/{md_file.name}"
                )
                continue
            dst.write_text(md_file.read_text(encoding="utf-8"), encoding="utf-8")
            actions.append(f"commands/{md_file.name} → {target_rel}")
        return actions

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

    # ---- context injection ----

    @property
    def context_injection(self) -> dict[str, Any]:
        """Platform context-loading / rules-distribution declaration.

        Declared in ``profile.yaml`` under ``context_injection``.  Consumed at
        deploy time to bake platform-specific artifacts (e.g. an ``@path``
        preamble in Claude Code's ``CLAUDE.md``, an ``instructions`` list in
        ``opencode.json``).  Adapters read from this property rather than
        hard-coding platform-specific paths.

        Returns an empty dict when the profile omits the section so adapters
        can gracefully fall back to legacy defaults.
        """
        return dict(self._profile.get("context_injection", {}) or {})

    def get_instruction_preamble(self) -> str:
        """Render the preamble block prepended to the instruction file body.

        Currently only used when ``context_injection.inline_file_syntax.kind``
        is ``at_mention`` (i.e. Claude Code / Cursor).  Returns an empty
        string for platforms that cannot cheaply reference files from inside
        their instruction file — those platforms rely on
        ``rules_distribution`` or explicit Read instructions instead.
        """
        ci = self.context_injection
        syntax = ci.get("inline_file_syntax", {}) or {}
        if syntax.get("kind") != "at_mention":
            return ""
        template = str(syntax.get("template") or "@{path}")
        files = (ci.get("auto_injection", {}) or {}).get("preamble_files") or []
        if not files:
            return ""
        lines = [template.format(path=p) for p in files]
        return "\n".join(lines) + "\n\n"

    # ---- MCP ----

    def inject_mcp_config(
        self,
        server_id: str,
        server_config: dict[str, Any],
        project_root: Path,
        *,
        dry_run: bool = False,
    ) -> list[str]:
        """Write MCP server config into the platform's configuration file.

        Default: merge into a JSON file under the standard ``mcpServers.<id>``
        key via :func:`merge_json_key`.  The concrete path comes from
        :meth:`_mcp_json_path` which subclasses override.  Platforms using a
        non-JSON or non-standard layout (e.g. Codex TOML, OpenCode's per-repo
        merge) override ``inject_mcp_config`` itself instead.
        """
        from cataforge.platform.helpers import merge_json_key

        mcp_path = self._mcp_json_path(project_root)
        return merge_json_key(
            mcp_path, f"mcpServers.{server_id}", server_config, dry_run=dry_run
        )

    def _mcp_json_path(self, project_root: Path) -> Path:
        """Return the JSON file path the default ``inject_mcp_config`` writes to.

        Subclasses that rely on the default implementation override this
        single method; adapters with fully custom MCP layouts override
        ``inject_mcp_config`` directly and can leave this raising.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must override either "
            "inject_mcp_config() or _mcp_json_path()"
        )


def _load_instruction_hashes(project_root: Path) -> dict[str, str]:
    path = project_root / _INSTRUCTION_HASHES_REL
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}


def _save_instruction_hashes(project_root: Path, hashes: dict[str, str]) -> None:
    path = project_root / _INSTRUCTION_HASHES_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(hashes, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
