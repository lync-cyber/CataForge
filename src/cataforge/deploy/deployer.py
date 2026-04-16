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
from cataforge.platform.base import PlatformAdapter
from cataforge.platform.registry import get_adapter

logger = logging.getLogger("cataforge.deploy")


class Deployer:
    """Orchestrate deployment for a given platform."""

    def __init__(self, config: ConfigManager, event_bus: EventBus | None = None) -> None:
        self._cfg = config
        self._bus = event_bus or EventBus()

    def deploy(self, platform_id: str, *, dry_run: bool = False) -> list[str]:
        """Execute a full deployment for *platform_id*. Returns action log.

        When *dry_run* is True, no files are written and actions describe what
        would be performed.
        """
        root = self._cfg.paths.root
        adapter = get_adapter(platform_id, self._cfg.paths.platforms_dir)
        actions: list[str] = []

        if adapter.needs_agent_deploy:
            actions.extend(
                adapter.deploy_agents(
                    self._cfg.paths.agents_dir, root, dry_run=dry_run
                )
            )

        actions.extend(
            adapter.deploy_instruction_files(
                self._cfg.paths.project_state_md,
                root,
                platform_id=platform_id,
                dry_run=dry_run,
            )
        )

        if adapter.hook_config_format:
            actions.extend(self._deploy_hooks(root, adapter, dry_run=dry_run))

        if adapter.additional_outputs:
            actions.extend(
                adapter.deploy_additional_outputs(
                    self._cfg.paths.rules_dir, root, dry_run=dry_run
                )
            )

        rules_dir = self._cfg.paths.rules_dir
        if rules_dir.is_dir():
            actions.extend(adapter.deploy_rules(rules_dir, root, dry_run=dry_run))

        skills_dir = self._cfg.paths.skills_dir
        if adapter.needs_skill_deploy and skills_dir.is_dir():
            actions.extend(adapter.deploy_skills(skills_dir, root, dry_run=dry_run))

        commands_dir = self._cfg.paths.commands_dir
        if adapter.needs_command_deploy and commands_dir.is_dir():
            actions.extend(adapter.deploy_commands(commands_dir, root, dry_run=dry_run))

        actions.extend(self._apply_degradation(root, adapter, dry_run=dry_run))
        actions.extend(self._deploy_mcp(root, platform_id, adapter, dry_run=dry_run))

        if not dry_run:
            self._write_deploy_state(root, platform_id)
        else:
            actions.append(
                f"would write deploy state → {self._cfg.paths.deploy_state} "
                f"(platform={platform_id})"
            )

        self._bus.emit(
            FRAMEWORK_DEPLOY,
            {"platform": platform_id, "actions": len(actions), "dry_run": dry_run},
        )
        return actions

    def _deploy_hooks(
        self, root: Path, adapter: PlatformAdapter, *, dry_run: bool = False
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
