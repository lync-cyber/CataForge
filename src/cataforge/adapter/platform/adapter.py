"""PlatformAdapter abstract base class.

All platform-specific differences are encapsulated here. The core runtime
NEVER imports platform-specific modules directly. Deploy algorithms live in
:mod:`cataforge.runtime.deploy.steps`; this class is the config / capability
carrier and the home for per-platform strategy hooks the steps read.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

from cataforge.adapter.platform.profile_schema import (
    CapabilityBinding,
    CapabilityContext,
    CapabilityResolution,
    HookPolicy,
    PlatformProfile,
)
from cataforge.utils.interpreter import hook_command_template


class PlatformAdapter(ABC):
    """Abstract base for all AI IDE platform adapters.

    A platform adapter is a config / capability carrier plus a set of
    per-platform strategy hooks. Deploy algorithms live in
    :mod:`cataforge.runtime.deploy.steps` and read these hooks; the adapter
    owns no deploy iteration of its own.
    """

    def __init__(self, profile: PlatformProfile) -> None:
        self._profile = profile

    @property
    @abstractmethod
    def platform_id(self) -> str: ...

    @property
    @abstractmethod
    def display_name(self) -> str: ...

    def capability_ids(self) -> set[str]:
        """Return all core and extended capability identifiers."""
        return set(self._profile.tool_map) | set(self._profile.extended_capabilities)

    def get_capability_binding(self, capability: str) -> CapabilityBinding | None:
        """Return the typed core/extended binding for *capability*."""
        return self._profile.tool_map.get(capability) or self._profile.extended_capabilities.get(
            capability
        )

    def resolve_capability(
        self,
        capability: str,
        context: CapabilityContext | None = None,
    ) -> CapabilityResolution:
        """Resolve static and conditional support for one capability."""
        binding = self.get_capability_binding(capability)
        if binding is None or binding.kind == "unsupported":
            return CapabilityResolution(
                capability=capability,
                tool=None,
                status="unsupported",
                available=False,
                reason="no platform capability binding",
            )

        clauses = binding.availability.any_of
        base_status: Literal["native", "replacement"] = (
            "replacement" if binding.kind == "replacement" else "native"
        )
        if not clauses:
            return CapabilityResolution(
                capability=capability,
                tool=binding.tool,
                status=base_status,
                available=True,
                hook_matchers=list(binding.hook_matchers),
            )
        if context is None:
            return CapabilityResolution(
                capability=capability,
                tool=binding.tool,
                status="conditional",
                available=None,
                hook_matchers=list(binding.hook_matchers),
                reason="runtime context required",
            )

        for clause in clauses:
            if clause.thread_scopes and context.thread_scope not in clause.thread_scopes:
                continue
            if (
                clause.collaboration_modes
                and context.collaboration_mode not in clause.collaboration_modes
            ):
                continue
            if not set(clause.required_features).issubset(context.enabled_features):
                continue
            return CapabilityResolution(
                capability=capability,
                tool=binding.tool,
                status=base_status,
                available=True,
                hook_matchers=list(binding.hook_matchers),
            )

        return CapabilityResolution(
            capability=capability,
            tool=binding.tool,
            status="conditional",
            available=False,
            hook_matchers=list(binding.hook_matchers),
            reason="runtime context does not satisfy availability clauses",
        )

    def resolve_tools_list(self, capabilities: list[str]) -> list[str]:
        resolved: list[str] = []
        for capability in capabilities:
            resolution = self.resolve_capability(capability)
            if resolution.available is not False and resolution.tool is not None:
                resolved.append(resolution.tool)
        return resolved

    def get_hook_command_template(self) -> str:
        """Return the hook command template with {module} placeholder.

        Hooks are invoked via ``"<sys.executable>" -m
        cataforge.runtime.hook.scripts.<module>`` — the deploying process's
        own interpreter, so the command imports cataforge regardless of how
        the package was installed (see :mod:`cataforge.utils.interpreter`).
        """
        return hook_command_template()

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
        return bool(self._profile.agent_definition.needs_deploy)

    @property
    def agent_layout(self) -> str:
        """Agent deploy layout: ``flat`` (one ``<name><suffix>`` per agent) or
        ``subdir`` (reproduce the ``<name>/AGENT.md`` tree)."""
        return str(self._profile.agent_definition.layout)

    def agent_target_rel(self) -> str | None:
        """Target dir (relative to project root) for flat-layout agent files.

        Defaults to ``scan_dirs[0]``; the profile's ``agent_definition.target_rel``
        overrides it for platforms that don't surface their agents path via
        ``scan_dirs`` (e.g. OpenCode's ``.opencode/agents``)."""
        declared = self._profile.agent_definition.target_rel
        if declared:
            return str(declared)
        scan_dirs = self.get_agent_scan_dirs()
        return scan_dirs[0] if scan_dirs else None

    @property
    def agent_file_suffix(self) -> str:
        """File extension flat-layout agents are written with (``.md`` / ``.toml``)."""
        return str(self._profile.agent_definition.file_suffix)

    @property
    def agent_head_signature(self) -> str:
        """Orphan-prune ownership signature for flat-layout agent files.

        The flat-prune helper removes a file only when its head bytes contain
        ``head_signature.format(stem=<file_stem>)``, so a user-authored file
        sharing the suffix survives."""
        return str(self._profile.agent_definition.head_signature)

    @property
    def agent_head_read_size(self) -> int:
        """Bytes scanned for :attr:`agent_head_signature` during orphan prune."""
        return int(self._profile.agent_definition.head_read_size)

    @property
    def prune_legacy_agent_subdirs(self) -> bool:
        """Whether flat-layout deploy also tears down leftover ``<name>/AGENT.md``
        subdirs from a prior dual-layout deploy."""
        return bool(self._profile.agent_definition.prune_legacy_subdirs)

    def render_agent(self, agent_id: str, content: str) -> str:
        """Produce the final flat-layout agent file body from translated content.

        Default: identity (Claude Code / OpenCode write the translated
        yaml-frontmatter verbatim). Subclasses override to wrap the body in a
        platform-native envelope (e.g. Codex TOML)."""
        del agent_id
        return content

    @property
    def reads_claude_md(self) -> bool:
        return bool(self._profile.instruction_file.reads_claude_md)

    @property
    def additional_outputs(self) -> list[dict[str, Any]]:
        return list(self._profile.instruction_file.additional_outputs)

    @property
    def instruction_targets(self) -> list[dict[str, Any]]:
        """Instruction artifacts this platform expects.

        Each entry uses:
        - ``type``: currently ``project_state_copy``
        - ``path``: relative output path (for example ``CLAUDE.md`` / ``AGENTS.md``)
        """
        targets = self._profile.instruction_file.targets
        if targets:
            return [dict(t) for t in targets if isinstance(t, dict)]
        if self.reads_claude_md:
            return [{"type": "project_state_copy", "path": "CLAUDE.md"}]
        return []

    @property
    def dispatch_info(self) -> dict[str, Any]:
        return self._profile.dispatch.model_dump(exclude_unset=True)

    @property
    def hook_config_format(self) -> str | None:
        return self._profile.hooks.config_format

    @property
    def hook_config_path(self) -> str | None:
        return self._profile.hooks.config_path

    @property
    def settings_defaults(self) -> dict[str, Any]:
        """Framework-owned default keys seeded into the platform settings file.

        Declared in ``profile.yaml`` under ``settings_defaults``; merged
        set-if-absent at deploy time so a user override is never clobbered.
        """
        return dict(self._profile.settings_defaults)

    @property
    def hook_event_map(self) -> dict[str, str | None]:
        return dict(self._profile.hooks.event_map)

    @property
    def hook_policies(self) -> dict[str, HookPolicy]:
        """Typed hook policies declared by the platform profile."""
        return dict(self._profile.hooks.policies)

    def get_hook_policy(self, hook_name: str) -> HookPolicy:
        """Return the declared policy or the native default."""
        if policy := self._profile.hooks.policies.get(hook_name):
            return policy
        return HookPolicy(mode="native")

    def resolve_hook_matcher(self, capability: str) -> str | None:
        """Resolve a hook matcher without conflating it with model tool names."""
        binding = self.get_capability_binding(capability)
        if binding and binding.hook_matchers:
            return "|".join(binding.hook_matchers)
        return binding.tool if binding else None

    @property
    def hook_entry_type(self) -> str | None:
        """Platform-native value for a hook entry's ``type`` field.

        Declared in ``profile.yaml`` under ``hooks.entry_type`` (e.g. Claude
        Code, Cursor and Codex all use ``"command"``).  When ``None`` the
        bridge falls back to the internal ``type`` from ``hooks.yaml`` — used
        only by platforms that do not emit JSON hook configs (e.g. OpenCode
        which uses plugins).
        """
        value = self._profile.hooks.entry_type
        return str(value) if value else None

    @property
    def needs_skill_deploy(self) -> bool:
        """Whether this platform wants skill definitions deployed to an IDE-visible path."""
        return bool(self._profile.skill_definition.needs_deploy)

    def get_skill_target_dir(self) -> str | None:
        """Target directory (relative to project root) for IDE-visible skills."""
        target = self._profile.skill_definition.target_dir
        return str(target) if target else None

    @property
    def needs_command_deploy(self) -> bool:
        """Whether this platform has a slash-command surface to deploy to."""
        return bool(self._profile.command_definition.needs_deploy)

    def get_command_target_dir(self) -> str | None:
        """Target directory (relative to project root) for IDE-visible slash commands."""
        target = self._profile.command_definition.target_dir
        return str(target) if target else None

    @property
    def agent_supported_fields(self) -> list[str]:
        """Agent frontmatter fields this platform supports.

        Declared in ``profile.yaml`` under ``agent_config.supported_fields``.
        Used by the translator/deployer to decide which fields to pass through.
        """
        return list(self._profile.agent_config.supported_fields)

    @property
    def agent_memory_scopes(self) -> list[str]:
        """Memory scopes the platform supports for agent-level persistence.

        Typical values: ``user``, ``project``, ``local``.
        """
        return list(self._profile.agent_config.memory_scopes)

    @property
    def agent_isolation_modes(self) -> list[str]:
        """Isolation modes the platform supports (e.g. ``worktree``)."""
        return list(self._profile.agent_config.isolation_modes)

    @property
    def agent_tool_policy(self) -> str:
        """Native per-agent tool-policy surface exposed by the platform."""
        return self._profile.agent_config.tool_policy

    def get_supported_features(self) -> dict[str, bool]:
        """Return platform feature flags.

        Declared in ``profile.yaml`` under ``features``.  These describe
        higher-order platform behaviors (cloud agents, agent teams, etc.),
        not per-tool mappings.
        """
        return dict(self._profile.features)

    def supports_feature(self, feature: str) -> bool:
        """Check whether a specific feature is supported."""
        return bool(self._profile.features.get(feature, False))

    @property
    def permission_modes(self) -> list[str]:
        """Permission/approval modes this platform supports.

        Declared in ``profile.yaml`` under ``permissions.modes``.
        """
        return list(self._profile.permissions.get("modes", []))

    @property
    def available_models(self) -> list[str]:
        """Models available on this platform for selection."""
        return list(self._profile.model_routing.available_models)

    @property
    def supports_per_agent_model(self) -> bool:
        """Whether the platform supports per-agent model selection."""
        return bool(self._profile.model_routing.per_agent_model)

    @property
    def user_resolved_model(self) -> bool:
        """Whether model selection is resolved at the user/runtime level.

        OpenCode (and any future provider-agnostic platform) lets the user
        choose models at runtime via Models.dev / config — agent files should
        not pin a specific model id. The deploy adapter omits ``model:`` for
        these platforms regardless of tier resolution.
        """
        return bool(self._profile.model_routing.user_resolved)

    def get_model_tier_map(self) -> dict[str, str | None]:
        """Tier → native model id map (e.g. ``{"light": "haiku", ...}``).

        Tiers are platform-agnostic capability levels (``light``, ``standard``,
        ``heavy``).  ``inherit`` and ``none`` are sentinel values handled by
        :meth:`resolve_agent_model` and never appear as keys here.

        Returns an empty dict when the platform omits the section — callers
        treat that as "no model can be resolved → omit ``model:``".
        """
        raw = self._profile.model_routing.tier_map
        return {str(k): (str(v) if v is not None else None) for k, v in raw.items()}

    def resolve_agent_model(self, tier: str | None) -> str | None:
        """Translate a ``model_tier:`` value into a platform-native model id.

        Returns ``None`` when the tier should not be written to the deployed
        agent file — covers four cases:

        * platform does not support per-agent models (e.g. Codex)
        * platform resolves models at the user/runtime level (e.g. OpenCode)
        * tier is ``none`` (agent opted out, e.g. orchestrator main-thread)
        * tier is ``inherit`` (agent defers to main-thread model)

        For ``light``/``standard``/``heavy`` we look up
        ``model_routing.tier_map`` from the profile.  Unknown tiers fall back
        to ``None`` (audit B7-α catches these in the source AGENT.md).
        """
        if not self.supports_per_agent_model:
            return None
        if self.user_resolved_model:
            return None
        if not tier or tier in {"none", "inherit"}:
            return None
        return self.get_model_tier_map().get(tier)

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
        return dict(self._profile.context_injection)

    def _default_rules_target_dir(self) -> str | None:
        """Return the platform's declared rule distribution directory, if any.

        Looks at ``context_injection.rules_distribution.target`` in the
        profile.  Used by the rules step and the runtime placeholder renderer
        so subclasses that only want to change wrapping (not the target path)
        share one source of truth."""
        target = (self.context_injection.get("rules_distribution", {}) or {}).get("target")
        return str(target) if target else None

    def wrap_rule_for_platform(self, name: str, content: str) -> tuple[str, str] | None:
        """Return ``(target_relpath, body)`` for an override rule, or ``None``.

        Default: copy verbatim to
        ``<context_injection.rules_distribution.target>/<name>.md`` when the
        profile declares a rules target; otherwise return ``None`` (skip).

        Subclasses override to:

        * change the wrapping (e.g. Cursor wraps as MDC with ``alwaysApply``)
        * change the target path
        * return ``None`` to suppress writing entirely (e.g. when the rule is
          surfaced through a different mechanism)
        """
        rules_target = self._default_rules_target_dir()
        if not rules_target:
            return None
        return (f"{rules_target}/{name}.md", content)

    def deploy_additional_outputs_hook(
        self,
        rules_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: Any = None,
        prior_manifest: set[str] | None = None,
    ) -> list[str]:
        """Generate platform-specific additional outputs (e.g. Cursor MDC rules).

        Default: no-op. Subclasses override to emit native artefacts whose
        format is platform-specific. The runtime step routes to this hook."""
        del rules_dir, project_root, dry_run, manifest, prior_manifest
        return []

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

    def post_instruction_deploy(
        self,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: Any = None,
    ) -> list[str]:
        """Register platform-native instruction artefacts after the base copy.

        Default: no-op. The instruction step writes the IDE's CLAUDE.md /
        AGENTS.md, then calls this hook so platforms that surface their
        instruction set through a config file (e.g. OpenCode's
        ``opencode.json#instructions``) can append it."""
        del project_root, dry_run, manifest
        return []

    def rules_target_relpath(self, platform_root: Path) -> str | None:
        """Relative target for the rendered ``.cataforge/rules`` copy.

        Default: ``<platform_root>/rules`` (where *platform_root* is the parent
        of the first agent scan dir). Return ``None`` to skip the base
        copy-render entirely — used by platforms that surface canonical rules
        through a different mechanism (e.g. Cursor's ``.cursor/rules/*.mdc``)."""
        return f"{platform_root.as_posix()}/rules"

    def emit_extra_rules(
        self,
        source_dir: Path,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: Any = None,
        force_copy: bool = False,
    ) -> list[str]:
        """Emit any platform-specific rule artefacts alongside the base copy.

        Default: no-op. Cursor uses this for the optional ``.claude/rules``
        cross-platform Markdown mirror."""
        del source_dir, project_root, dry_run, manifest, force_copy
        return []

    def mcp_json_path(self, project_root: Path) -> Path:
        """JSON file the default :meth:`write_mcp_config` writes to.

        Platforms that rely on the default JSON merge override this single
        method; platforms with a fully custom MCP layout (e.g. Codex TOML,
        OpenCode's per-repo merge) override :meth:`write_mcp_config` and can
        leave this raising."""
        raise NotImplementedError(
            f"{type(self).__name__} must override either write_mcp_config() or mcp_json_path()"
        )

    def _native_mcp_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Translate a neutral registry MCP payload to this platform's shape.

        Default passthrough: stdio servers (``command``/``args``/``env``) and any
        payload the platform's config schema already accepts verbatim. Platforms
        whose remote (HTTP/SSE) server entry differs from the neutral
        ``{transport, url}`` form override this to emit their native spelling."""
        return payload

    def write_mcp_config(
        self,
        server_id: str,
        server_config: dict[str, Any],
        project_root: Path,
        *,
        dry_run: bool = False,
    ) -> list[str]:
        """Write one MCP server config into the platform's configuration file.

        Default: render via :meth:`_native_mcp_payload`, then merge into a JSON
        file under ``mcpServers.<id>`` at :meth:`mcp_json_path`. Platforms using a
        non-JSON or non-standard layout override this hook directly."""
        from cataforge.adapter.platform.hooks_config import merge_json_key

        native = self._native_mcp_payload(server_config)
        mcp_path = self.mcp_json_path(project_root)
        return merge_json_key(mcp_path, f"mcpServers.{server_id}", native, dry_run=dry_run)

    def enable_project_mcp_server(
        self, server_id: str, project_root: Path, *, dry_run: bool = False
    ) -> list[str]:
        """Pre-approve a project MCP server so it connects without a per-session
        prompt. No-op for platforms with no such enablement gate; overridden by
        those that have one (e.g. Claude Code's ``enabledMcpjsonServers``)."""
        return []
