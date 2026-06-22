"""Deployment orchestrator.

Adapter-driven design: all platform-specific logic lives in PlatformAdapter.
The Deployer never inspects concrete adapter types.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field
from importlib.resources import as_file
from pathlib import Path

from cataforge.adapter.platform.adapter import PlatformAdapter
from cataforge.adapter.platform.registry import get_adapter
from cataforge.core.config import ConfigManager
from cataforge.core.errors import ConfigError
from cataforge.core.events import FRAMEWORK_DEPLOY, EventBus
from cataforge.core.io import read_json
from cataforge.core.scaffold import packaged_instruction_template
from cataforge.runtime.deploy.manifest import (
    DeployManifest,
    load_prior_manifest,
    load_prior_manifest_platform,
    save_manifest,
)
from cataforge.utils.atomic_write import atomic_write_text

logger = logging.getLogger("cataforge.runtime.deploy")


@dataclass
class DeployContext:
    """Shared state threaded through every deploy step."""

    root: Path
    adapter: PlatformAdapter
    manifest: DeployManifest
    prior_owned: set[str]
    platform_id: str
    dry_run: bool
    include_maintainer_only: bool
    force_copy: bool
    stack: ExitStack
    cfg: ConfigManager
    agents_src: Path = field(default_factory=Path)
    skills_src: Path = field(default_factory=Path)
    instruction_src: Path = field(default_factory=Path)


# ---------------------------------------------------------------------------
# Step type alias
# ---------------------------------------------------------------------------

_StepFn = Callable[["Deployer", DeployContext], list[str]]
_GuardFn = Callable[[DeployContext], bool]


def _always(_ctx: DeployContext) -> bool:
    return True


def _section_merge_target_rels(adapter: PlatformAdapter) -> set[str]:
    """Instruction-file targets whose state lives in the file itself.

    ``section-merge`` reads the existing target as its own merge source, so
    purging it drops the orchestrator-owned sections the next deploy can only
    recover from that file. ``overwrite`` targets hold no such state and stay
    purgeable.
    """
    rels: set[str] = set()
    for target in adapter.instruction_targets:
        if str(target.get("update_strategy", "overwrite")) != "section-merge":
            continue
        rel = str(target.get("path", ""))
        if rel:
            rels.add(rel)
    return rels


class Deployer:
    """Orchestrate deployment for a given platform."""

    def __init__(self, config: ConfigManager, event_bus: EventBus | None = None) -> None:
        self._cfg = config
        self._bus = event_bus or EventBus()

    def deploy(
        self,
        platform_id: str,
        *,
        dry_run: bool = False,
        include_maintainer_only: bool = False,
        force_copy: bool = False,
        rebuild: bool = False,
    ) -> list[str]:
        """Execute a full deployment for *platform_id*. Returns action log.

        Thin wrapper owning an :class:`ExitStack`, so any override-resolution
        staging dir is cleaned up on return or exception. The real work lives
        in :meth:`_deploy`.
        """
        with ExitStack() as stack:
            return self._deploy(
                platform_id,
                stack,
                dry_run=dry_run,
                include_maintainer_only=include_maintainer_only,
                force_copy=force_copy,
                rebuild=rebuild,
            )

    def _deploy(
        self,
        platform_id: str,
        stack: ExitStack,
        *,
        dry_run: bool = False,
        include_maintainer_only: bool = False,
        force_copy: bool = False,
        rebuild: bool = False,
    ) -> list[str]:
        """Run the full deployment pipeline (see :meth:`deploy`).

        When *dry_run* is True, no files are written and actions describe what
        would be performed. When *include_maintainer_only* is True, skills
        whose SKILL.md frontmatter declares ``maintainer-only: true`` are
        also linked into the IDE (off by default — those skills operate on
        upstream maintenance workflows and would only bloat prompt context
        for downstream users).

        ``force_copy`` makes the symlink/junction step fall straight through
        to copy, so destructive deletes inside ``.claude/skills/<name>/``
        only affect the IDE-side copy and never propagate back to source.

        ``rebuild`` first removes every path the previous deploy claimed
        ownership of (per the manifest), then performs a regular deploy.
        Used to recover from a corrupt or partial prior deploy.

        Idempotency contract — two invariants this method enforces:

        1. **Self-heal** — at entry we call
           ``copy_scaffold_to(force=False)`` so any ``.cataforge/`` file the
           user deleted (directly or through a junction) gets restored from
           the bundled wheel before we try to translate it.  Existing files
           are never overwritten by self-heal.
        2. **Ownership-scoped prune** — every adapter receives a
           ``DeployManifest`` and a prior-manifest snapshot. Prune steps may
           only delete entries that were in the prior manifest, so
           user-authored files (e.g. a hand-written
           ``.claude/commands/foo.md``) survive every redeploy.
        """
        root = self._cfg.paths.root
        adapter = get_adapter(platform_id, self._cfg.paths.platforms_dir)
        actions: list[str] = []
        prior_owned = load_prior_manifest(root)
        manifest = DeployManifest(platform_id)

        # Pre-pipeline: rebuild purge (must run before self-heal so the prior
        # manifest reflects reality at purge time).
        if rebuild:
            actions.extend(
                self._rebuild_purge(
                    root,
                    prior_owned,
                    platform_id=platform_id,
                    prior_platform=load_prior_manifest_platform(root),
                    dry_run=dry_run,
                    protect=_section_merge_target_rels(adapter),
                )
            )
            prior_owned = set()

        # Pre-pipeline: self-heal missing scaffold files.
        actions.extend(self._self_heal_scaffold(dry_run=dry_run))

        # Pre-pipeline: resolve override/plugin/language layers.
        agents_src, skills_src, stage_action = self._resolve_override_sources(stack)
        if stage_action:
            actions.append(stage_action)

        # Resolve instruction template source (consumes an ExitStack slot).
        instruction_src = stack.enter_context(as_file(packaged_instruction_template()))

        ctx = DeployContext(
            root=root,
            adapter=adapter,
            manifest=manifest,
            prior_owned=prior_owned,
            platform_id=platform_id,
            dry_run=dry_run,
            include_maintainer_only=include_maintainer_only,
            force_copy=force_copy,
            stack=stack,
            cfg=self._cfg,
            agents_src=agents_src,
            skills_src=skills_src,
            instruction_src=instruction_src,
        )

        for _name, guard, step in self._STEPS:
            if guard(ctx):
                actions.extend(step(self, ctx))

        # Tail: write state and manifest (or dry-run notes).
        if not dry_run:
            self._write_deploy_state(root, platform_id)
            from cataforge import __version__
            from cataforge.runtime.deploy.drift import compute_source_digest

            manifest.source_digest = compute_source_digest(self._cfg.paths)
            manifest.package_version = __version__
            save_manifest(root, manifest)
        else:
            actions.append(
                f"would write deploy state → {self._cfg.paths.deploy_state} "
                f"(platform={platform_id})"
            )
            actions.append(f"would write deploy manifest ({len(manifest.owned)} owned path(s))")

        self._bus.emit(
            FRAMEWORK_DEPLOY,
            {"platform": platform_id, "actions": len(actions), "dry_run": dry_run},
        )
        return actions

    # ---- Step implementations ----

    def _step_deploy_agents(self, ctx: DeployContext) -> list[str]:
        from cataforge.runtime.deploy.steps import deploy_agents

        return deploy_agents(
            ctx.adapter,
            ctx.agents_src,
            ctx.root,
            dry_run=ctx.dry_run,
            manifest=ctx.manifest,
            prior_manifest=ctx.prior_owned,
        )

    def _step_deploy_instruction_files(self, ctx: DeployContext) -> list[str]:
        from cataforge.runtime.deploy.steps import deploy_instruction_files

        return deploy_instruction_files(
            ctx.adapter,
            ctx.instruction_src,
            ctx.root,
            platform_id=ctx.platform_id,
            design_tool=ctx.cfg.design_tool,
            dry_run=ctx.dry_run,
            manifest=ctx.manifest,
            prior_manifest=ctx.prior_owned,
        )

    def _step_deploy_hooks(self, ctx: DeployContext) -> list[str]:
        return self._deploy_hooks(ctx.root, ctx.adapter, manifest=ctx.manifest, dry_run=ctx.dry_run)

    def _step_deploy_additional_outputs(self, ctx: DeployContext) -> list[str]:
        from cataforge.runtime.deploy.steps import deploy_additional_outputs

        return deploy_additional_outputs(
            ctx.adapter,
            ctx.cfg.paths.rules_dir,
            ctx.root,
            dry_run=ctx.dry_run,
            manifest=ctx.manifest,
            prior_manifest=ctx.prior_owned,
        )

    def _step_deploy_rules(self, ctx: DeployContext) -> list[str]:
        from cataforge.runtime.deploy.steps import deploy_rules

        return deploy_rules(
            ctx.adapter,
            ctx.cfg.paths.rules_dir,
            ctx.root,
            dry_run=ctx.dry_run,
            manifest=ctx.manifest,
            prior_manifest=ctx.prior_owned,
            force_copy=ctx.force_copy,
        )

    def _step_deploy_skills(self, ctx: DeployContext) -> list[str]:
        from cataforge.runtime.deploy.steps import deploy_skills

        return deploy_skills(
            ctx.adapter,
            ctx.skills_src,
            ctx.root,
            dry_run=ctx.dry_run,
            include_maintainer_only=ctx.include_maintainer_only,
            manifest=ctx.manifest,
            prior_manifest=ctx.prior_owned,
            force_copy=ctx.force_copy,
        )

    def _step_deploy_commands(self, ctx: DeployContext) -> list[str]:
        from cataforge.runtime.deploy.steps import deploy_commands

        return deploy_commands(
            ctx.adapter,
            ctx.cfg.paths.commands_dir,
            ctx.root,
            dry_run=ctx.dry_run,
            manifest=ctx.manifest,
            prior_manifest=ctx.prior_owned,
        )

    def _step_apply_degradation(self, ctx: DeployContext) -> list[str]:
        return self._apply_degradation(ctx.root, ctx.adapter, dry_run=ctx.dry_run)

    def _step_deploy_overrides_rules(self, ctx: DeployContext) -> list[str]:
        from cataforge.runtime.deploy.steps import deploy_overrides_rules

        return deploy_overrides_rules(
            ctx.adapter, ctx.root, dry_run=ctx.dry_run, manifest=ctx.manifest
        )

    def _step_deploy_mcp(self, ctx: DeployContext) -> list[str]:
        return self._deploy_mcp(
            ctx.root, ctx.platform_id, ctx.adapter, manifest=ctx.manifest, dry_run=ctx.dry_run
        )

    # ---- Guard functions ----

    @staticmethod
    def _guard_agents(ctx: DeployContext) -> bool:
        return ctx.adapter.needs_agent_deploy

    @staticmethod
    def _guard_hooks(ctx: DeployContext) -> bool:
        return bool(ctx.adapter.hook_config_format)

    @staticmethod
    def _guard_additional_outputs(ctx: DeployContext) -> bool:
        return bool(ctx.adapter.additional_outputs)

    @staticmethod
    def _guard_rules(ctx: DeployContext) -> bool:
        return ctx.cfg.paths.rules_dir.is_dir()

    @staticmethod
    def _guard_skills(ctx: DeployContext) -> bool:
        return ctx.adapter.needs_skill_deploy and ctx.skills_src.is_dir()

    @staticmethod
    def _guard_commands(ctx: DeployContext) -> bool:
        return ctx.adapter.needs_command_deploy and ctx.cfg.paths.commands_dir.is_dir()

    # ---- Ordered step pipeline ----
    # Each entry: (name, guard, step_method)
    # Order matches the original _deploy() sequence exactly.
    # apply_degradation must precede deploy_overrides_rules.

    _STEPS: list[tuple[str, _GuardFn, _StepFn]] = [
        ("agents", _guard_agents.__func__, _step_deploy_agents),  # type: ignore[attr-defined]
        ("instruction_files", _always, _step_deploy_instruction_files),
        ("hooks", _guard_hooks.__func__, _step_deploy_hooks),  # type: ignore[attr-defined]
        ("additional_outputs", _guard_additional_outputs.__func__, _step_deploy_additional_outputs),  # type: ignore[attr-defined]
        ("rules", _guard_rules.__func__, _step_deploy_rules),  # type: ignore[attr-defined]
        ("skills", _guard_skills.__func__, _step_deploy_skills),  # type: ignore[attr-defined]
        ("commands", _guard_commands.__func__, _step_deploy_commands),  # type: ignore[attr-defined]
        ("degradation", _always, _step_apply_degradation),
        ("overrides_rules", _always, _step_deploy_overrides_rules),
        ("mcp", _always, _step_deploy_mcp),
    ]

    # ---- P1 plan A: self-heal .cataforge/ from bundled scaffold ----

    def _self_heal_scaffold(self, *, dry_run: bool = False) -> list[str]:
        """Refill any missing ``.cataforge/`` files from the bundled wheel.

        ``copy_scaffold_to(force=False, backup=False)`` writes only when the
        target file is *absent*, so user-edited source files are never
        touched. The reason this exists at deploy entry rather than only in
        ``cataforge setup``: a single mis-click inside a junction-mounted
        ``.claude/skills/<name>/`` will delete the source file, and the
        only thing left for the user to do is ``cataforge deploy`` again —
        so deploy has to be the recovery path.
        """
        from cataforge.core.scaffold import copy_scaffold_to

        cataforge_dir = self._cfg.paths.cataforge_dir
        if not cataforge_dir.is_dir():
            return []

        if dry_run:
            return ["would self-heal missing .cataforge/ files (force=False)"]

        try:
            written = copy_scaffold_to(cataforge_dir, force=False, backup=False).written
        except FileNotFoundError as exc:
            logger.debug("self-heal skipped: %s", exc)
            return []
        if not written:
            return []
        self._cfg.reload()
        return [f"self-heal: restored {len(written)} missing scaffold file(s) from bundled wheel"]

    # ---- P1: resolve user/project override layers ----

    def _resolve_override_sources(self, stack: ExitStack) -> tuple[Path, Path, str | None]:
        """Return the (agents, skills) source dirs deploy should read from.

        Stages a layered, section-patched, plugin-merged tree into a temp dir
        (cleaned up via *stack*) when overrides, plugin contributions, or
        language-aware agents need it; otherwise returns the scaffold dirs
        unchanged so the common path stays byte-identical to the pre-overrides
        flow.
        """
        from cataforge.core.languages import active_languages
        from cataforge.core.layers import has_overrides
        from cataforge.runtime.assets.resolver import resolve_kind
        from cataforge.runtime.deploy.lang_fragments import inject_into_staged_agents
        from cataforge.runtime.plugin.loader import PluginLoader

        paths = self._cfg.paths
        plugins = PluginLoader(paths.root)
        plugin_agents = plugins.provided_agent_dirs()
        plugin_skills = plugins.provided_skill_dirs()
        overrides = has_overrides(paths)
        langs = active_languages(self._cfg)

        need_agents = overrides or bool(plugin_agents) or bool(langs)
        need_skills = overrides or bool(plugin_skills)
        if not need_agents and not need_skills:
            return paths.agents_dir, paths.skills_dir, None

        staging = Path(tempfile.mkdtemp(prefix="cataforge-deploy-"))
        stack.callback(shutil.rmtree, staging, ignore_errors=True)
        agents_src, skills_src = paths.agents_dir, paths.skills_dir
        bits: list[str] = []
        if need_agents:
            resolve_kind(paths, "agents", staging / "agents", plugin_dirs=plugin_agents)
            inject_into_staged_agents(staging / "agents", langs, paths)
            agents_src = staging / "agents"
            bits.append("agents")
        if need_skills:
            resolve_kind(paths, "skills", staging / "skills", plugin_dirs=plugin_skills)
            skills_src = staging / "skills"
            bits.append("skills")
        return (
            agents_src,
            skills_src,
            f"resolved override/plugin/language layers for {' + '.join(bits)}",
        )

    # ---- P3: --rebuild prunes prior-owned paths before deploy ----

    def _rebuild_purge(
        self,
        root: Path,
        prior_owned: set[str],
        *,
        platform_id: str,
        prior_platform: str | None,
        dry_run: bool = False,
        protect: set[str] | None = None,
    ) -> list[str]:
        """Remove every path the prior manifest claimed.

        Symmetric to a normal prune pass but applied wholesale: we use
        ``_remove_target`` so symlinks, junctions, files and real dirs all
        wash out the same way. User-authored paths that were never in the
        manifest are not touched. Paths in *protect* (section-merge instruction
        targets) are kept too — their state lives in the file the next deploy
        merges back into, so purging them is silent data loss.

        Refuses to purge when the prior manifest belongs to a *different*
        platform than the one we're about to deploy: rebuilding cursor
        after a claude-code deploy (or vice versa) would otherwise blast
        away paths that the new platform is about to author from scratch
        — silent, irreversible data loss for any user-edited file under
        ``.claude/`` / ``.cursor/`` that the new platform doesn't own.
        Switching platforms is a deliberate two-step: clean up the old
        target manually (``rm -rf .claude/`` etc.) then deploy fresh.
        """
        from cataforge.adapter.platform.fileops import _remove_target

        if not prior_owned:
            return ["rebuild: no prior manifest — nothing to purge"]
        if prior_platform is not None and prior_platform != platform_id:
            return [
                f"WARN: rebuild-purge skipped — prior deploy was "
                f"{prior_platform!r} but this run targets "
                f"{platform_id!r}. Remove the old platform's artefacts "
                f"manually before switching, otherwise this purge would "
                f"erase files the new platform never owned."
            ]
        protect = protect or set()
        actions: list[str] = []
        for rel in sorted(prior_owned):
            if rel in protect:
                actions.append(
                    f"rebuild: preserved {rel} (section-merge target — "
                    f"purge would drop merged state)"
                )
                continue
            target = root / rel
            if not target.exists() and not target.is_symlink():
                continue
            if dry_run:
                actions.append(f"would rebuild-purge {rel}")
            else:
                try:
                    _remove_target(target)
                    actions.append(f"rebuild-purged {rel}")
                except OSError as exc:
                    actions.append(f"WARN: rebuild-purge {rel} failed — {exc}")
        return actions

    def _deploy_hooks(
        self,
        root: Path,
        adapter: PlatformAdapter,
        *,
        manifest: DeployManifest | None = None,
        dry_run: bool = False,
    ) -> list[str]:
        from cataforge.runtime.hook.bridge import generate_platform_hooks

        try:
            hooks_config, warnings = generate_platform_hooks(adapter)
        except (ImportError, AttributeError) as e:
            logger.exception("hook generation failed (likely plugin issue)")
            return [
                f"hooks: generation failed — {type(e).__name__}: {e}. "
                f"Check that plugins providing hooks are installed and "
                f"compatible; full traceback in logs."
            ]
        except Exception as e:
            logger.exception("hook generation failed")
            return [f"hooks: generation failed — {type(e).__name__}: {e}. Full traceback in logs."]

        config_path_str = adapter.hook_config_path
        actions: list[str] = [f"WARN: {w}" for w in warnings]

        if not config_path_str:
            return actions

        config_path = root / config_path_str
        if dry_run:
            actions.append(
                f"would merge hooks into {config_path_str} ({len(hooks_config)} event(s))"
            )
            return actions

        config_path.parent.mkdir(parents=True, exist_ok=True)

        if config_path.is_file():
            try:
                existing = read_json(config_path)
            except ConfigError as e:
                logger.warning("Overwriting invalid hook config %s: %s", config_path, e)
                existing = {}
        else:
            existing = {}

        from cataforge.adapter.platform.hooks_config import merge_hooks_config

        template = adapter.get_hook_command_template()
        owned_prefixes = (template.split("{module}")[0], "python .cataforge/hooks/custom/")
        existing["hooks"] = merge_hooks_config(
            existing.get("hooks", {}), hooks_config, owned_prefixes
        )
        atomic_write_text(config_path, json.dumps(existing, indent=2, ensure_ascii=False) + "\n")
        if manifest is not None:
            manifest.record(config_path_str)
        actions.append(f"hooks → {config_path_str}")
        return actions

    def _apply_degradation(
        self, root: Path, adapter: PlatformAdapter, *, dry_run: bool = False
    ) -> list[str]:
        from cataforge.runtime.hook.bridge import apply_degradation

        try:
            return apply_degradation(adapter, root, dry_run=dry_run)
        except (ImportError, AttributeError) as e:
            logger.exception("degradation failed (likely plugin issue)")
            return [
                f"degradation: skipped — {type(e).__name__}: {e}. "
                f"Check plugin compatibility; full traceback in logs."
            ]
        except Exception as e:
            logger.exception("degradation failed")
            return [f"degradation: skipped — {type(e).__name__}: {e}. Full traceback in logs."]

    def _deploy_mcp(
        self,
        root: Path,
        platform_id: str,
        adapter: PlatformAdapter,
        *,
        manifest: DeployManifest | None = None,
        dry_run: bool = False,
    ) -> list[str]:
        from cataforge.runtime.deploy.steps import inject_mcp_config
        from cataforge.runtime.mcp.registry import MCPRegistry

        registry = MCPRegistry(root)
        actions: list[str] = []
        for server in registry.list_servers():
            payload = registry.get_platform_config(server.id, platform_id)
            if not payload:
                actions.append(f"SKIP: mcp.{server.id} — empty platform payload")
                continue
            actions.extend(inject_mcp_config(adapter, server.id, payload, root, dry_run=dry_run))
        return actions

    def _write_deploy_state(self, root: Path, platform_id: str) -> None:
        state_file = self._cfg.paths.deploy_state
        atomic_write_text(state_file, json.dumps({"platform": platform_id}, indent=2) + "\n")
