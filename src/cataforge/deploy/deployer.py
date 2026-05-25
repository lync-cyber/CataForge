"""Deployment orchestrator.

Adapter-driven design: all platform-specific logic lives in PlatformAdapter.
The Deployer never inspects concrete adapter types.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from cataforge.core.config import ConfigManager
from cataforge.core.events import FRAMEWORK_DEPLOY, EventBus
from cataforge.deploy.manifest import (
    DeployManifest,
    load_prior_manifest,
    save_manifest,
)
from cataforge.platform.base import PlatformAdapter
from cataforge.platform.registry import get_adapter

logger = logging.getLogger("cataforge.deploy")


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

        if rebuild:
            actions.extend(self._rebuild_purge(root, prior_owned, dry_run=dry_run))
            # After a purge the prior manifest no longer reflects reality;
            # treat downstream prune passes as a fresh start so nothing
            # else gets second-guessed.
            prior_owned = set()

        # P1 plan A — refill any source files the user deleted before we
        # try to render IDE artefacts from them.
        actions.extend(self._self_heal_scaffold(dry_run=dry_run))

        if adapter.needs_agent_deploy:
            actions.extend(
                adapter.deploy_agents(
                    self._cfg.paths.agents_dir,
                    root,
                    dry_run=dry_run,
                    manifest=manifest,
                    prior_manifest=prior_owned,
                )
            )

        actions.extend(
            adapter.deploy_instruction_files(
                self._cfg.paths.project_state_md,
                root,
                platform_id=platform_id,
                dry_run=dry_run,
                manifest=manifest,
                prior_manifest=prior_owned,
            )
        )

        if adapter.hook_config_format:
            actions.extend(
                self._deploy_hooks(root, adapter, manifest=manifest, dry_run=dry_run)
            )

        if adapter.additional_outputs:
            actions.extend(
                adapter.deploy_additional_outputs(
                    self._cfg.paths.rules_dir,
                    root,
                    dry_run=dry_run,
                    manifest=manifest,
                    prior_manifest=prior_owned,
                )
            )

        rules_dir = self._cfg.paths.rules_dir
        if rules_dir.is_dir():
            actions.extend(
                adapter.deploy_rules(
                    rules_dir,
                    root,
                    dry_run=dry_run,
                    manifest=manifest,
                    prior_manifest=prior_owned,
                    force_copy=force_copy,
                )
            )

        skills_dir = self._cfg.paths.skills_dir
        if adapter.needs_skill_deploy and skills_dir.is_dir():
            actions.extend(
                adapter.deploy_skills(
                    skills_dir,
                    root,
                    dry_run=dry_run,
                    include_maintainer_only=include_maintainer_only,
                    manifest=manifest,
                    prior_manifest=prior_owned,
                    force_copy=force_copy,
                )
            )

        commands_dir = self._cfg.paths.commands_dir
        if adapter.needs_command_deploy and commands_dir.is_dir():
            actions.extend(
                adapter.deploy_commands(
                    commands_dir,
                    root,
                    dry_run=dry_run,
                    manifest=manifest,
                    prior_manifest=prior_owned,
                )
            )

        actions.extend(self._apply_degradation(root, adapter, dry_run=dry_run))
        actions.extend(
            self._deploy_mcp(
                root, platform_id, adapter, manifest=manifest, dry_run=dry_run
            )
        )

        if not dry_run:
            self._write_deploy_state(root, platform_id)
            save_manifest(root, manifest)
        else:
            actions.append(
                f"would write deploy state → {self._cfg.paths.deploy_state} "
                f"(platform={platform_id})"
            )
            actions.append(
                f"would write deploy manifest "
                f"({len(manifest.owned)} owned path(s))"
            )

        self._bus.emit(
            FRAMEWORK_DEPLOY,
            {"platform": platform_id, "actions": len(actions), "dry_run": dry_run},
        )
        return actions

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
            # Fresh project — ``cataforge setup`` is the right entry point;
            # ``deploy`` should not silently scaffold from nothing.
            return []

        if dry_run:
            # We don't probe the wheel during dry-run — it's expensive and
            # the user has already been told it's a dry-run.
            return ["would self-heal missing .cataforge/ files (force=False)"]

        try:
            written, _, _ = copy_scaffold_to(
                cataforge_dir, force=False, backup=False
            )
        except FileNotFoundError as exc:
            # Editable install with no bundled scaffold visible — log and
            # carry on. ``setup`` will have already populated the dir.
            logger.debug("self-heal skipped: %s", exc)
            return []
        if not written:
            return []
        # Reset the config cache so the rest of deploy sees the restored
        # framework.json (if that was one of the files we just refilled).
        self._cfg.reload()
        return [
            f"self-heal: restored {len(written)} missing scaffold file(s) "
            f"from bundled wheel"
        ]

    # ---- P3: --rebuild prunes prior-owned paths before deploy ----

    def _rebuild_purge(
        self,
        root: Path,
        prior_owned: set[str],
        *,
        dry_run: bool = False,
    ) -> list[str]:
        """Remove every path the prior manifest claimed.

        Symmetric to a normal prune pass but applied wholesale: we use
        ``_remove_target`` so symlinks, junctions, files and real dirs all
        wash out the same way. User-authored paths that were never in the
        manifest are not touched.
        """
        from cataforge.platform.helpers import _remove_target

        if not prior_owned:
            return ["rebuild: no prior manifest — nothing to purge"]
        actions: list[str] = []
        for rel in sorted(prior_owned):
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
        from cataforge.hook.bridge import generate_platform_hooks

        try:
            hooks_config, warnings = generate_platform_hooks(adapter)
        except Exception as e:
            return [f"hooks: generation failed — {e}"]

        config_path_str = adapter.hook_config_path
        actions: list[str] = [f"WARN: {w}" for w in warnings]

        if not config_path_str:
            return actions

        config_path = root / config_path_str
        if dry_run:
            actions.append(
                f"would merge hooks into {config_path_str} "
                f"({len(hooks_config)} event(s))"
            )
            return actions

        config_path.parent.mkdir(parents=True, exist_ok=True)

        if config_path.is_file():
            try:
                existing = json.loads(config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Overwriting invalid hook config %s: %s", config_path, e)
                existing = {}
        else:
            existing = {}

        existing["hooks"] = hooks_config
        config_path.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if manifest is not None:
            manifest.record(config_path_str)
        actions.append(f"hooks → {config_path_str}")
        return actions

    def _apply_degradation(
        self, root: Path, adapter: PlatformAdapter, *, dry_run: bool = False
    ) -> list[str]:
        from cataforge.hook.bridge import apply_degradation

        try:
            return apply_degradation(adapter, root, dry_run=dry_run)
        except Exception as e:
            return [f"degradation: skipped — {e}"]

    def _deploy_mcp(
        self,
        root: Path,
        platform_id: str,
        adapter: PlatformAdapter,
        *,
        manifest: DeployManifest | None = None,
        dry_run: bool = False,
    ) -> list[str]:
        from cataforge.mcp.registry import MCPRegistry

        registry = MCPRegistry(root)
        actions: list[str] = []
        for server in registry.list_servers():
            payload = registry.get_platform_config(server.id, platform_id)
            if not payload:
                actions.append(f"SKIP: mcp.{server.id} — empty platform payload")
                continue
            actions.extend(
                adapter.inject_mcp_config(
                    server.id, payload, root, dry_run=dry_run
                )
            )
        return actions

    def _write_deploy_state(self, root: Path, platform_id: str) -> None:
        state_file = self._cfg.paths.deploy_state
        state_file.write_text(
            json.dumps({"platform": platform_id}, indent=2) + "\n",
            encoding="utf-8",
        )
