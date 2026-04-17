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
        # The instructions list is declared in profile.context_injection so it
        # stays auditable alongside the rest of the platform surface.  Fall
        # back to the legacy literal if the profile omits the section so older
        # scaffolds keep working without touching this code.
        ci = self.context_injection
        rd = ci.get("rules_distribution", {}) or {}
        instructions = list(rd.get("files") or ["AGENTS.md", ".cataforge/rules/*.md"])
        actions.extend(
            merge_json_key(
                project_root / "opencode.json",
                "instructions",
                instructions,
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

    # ---- hooks (OpenCode plugin-based surface) -----------------------

    def emit_plugin_hooks(
        self, project_root: Path, *, dry_run: bool = False
    ) -> list[str]:
        """Generate a TypeScript plugin that bridges OpenCode events to the
        CataForge Python hook scripts.

        OpenCode doesn't accept JSON hook configs — it loads ``.ts`` plugins
        that subscribe to events like ``tool.execute.before``.  The generated
        plugin ``spawn``s each canonical hook's Python script with the event
        payload on stdin, exactly matching how Claude Code / Cursor invoke
        the same scripts.  The end result: the same ``guard_dangerous`` /
        ``lint_format`` / etc. code runs on every supported platform.
        """
        from cataforge.hook.bridge import load_hooks_spec

        try:
            spec = load_hooks_spec()
        except (OSError, ValueError) as exc:
            return [f"opencode plugin: load hooks.yaml failed — {exc}"]

        event_map = self.hook_event_map
        active_events: dict[str, list[dict[str, Any]]] = {}
        for canonical_event, entries in (spec.get("hooks") or {}).items():
            plugin_event = event_map.get(canonical_event)
            if not plugin_event:
                continue
            active_events.setdefault(plugin_event, []).extend(entries or [])

        if not active_events:
            return ["opencode plugin: no events mapped — skipping"]

        plugin_path = project_root / ".opencode" / "plugins" / "cataforge-hooks.ts"
        content = _render_opencode_plugin(active_events)

        if dry_run:
            return [
                f"would write {plugin_path.relative_to(project_root)} "
                f"({len(active_events)} event(s))"
            ]

        plugin_path.parent.mkdir(parents=True, exist_ok=True)
        plugin_path.write_text(content, encoding="utf-8")
        return [f"opencode plugin → {plugin_path.relative_to(project_root)}"]


def _render_opencode_plugin(active_events: dict[str, list[dict[str, Any]]]) -> str:
    """Render the TS plugin source.  Kept free-standing for testability."""
    import json as _json

    # Build an event → list[{script, matcher_capability}] descriptor the TS
    # side can iterate.  All business logic lives in Python; the TS plugin
    # is a thin dispatcher.
    descriptor: dict[str, list[dict[str, str]]] = {}
    for plugin_event, entries in active_events.items():
        descriptor[plugin_event] = []
        for entry in entries:
            script = str(entry.get("script", "")).replace(".py", "")
            if not script:
                continue
            descriptor[plugin_event].append(
                {
                    "script": script,
                    "matcher_capability": str(
                        entry.get("matcher_capability", "")
                    ),
                    "type": str(entry.get("type", "observe")),
                }
            )

    events_json = _json.dumps(descriptor, indent=2, ensure_ascii=False)

    return (
        "// Auto-generated by `cataforge deploy` — do not edit.\n"
        "// This plugin bridges OpenCode runtime events to CataForge's\n"
        "// Python hook scripts so one hooks.yaml controls every platform.\n"
        "// Regenerate with: cataforge deploy --platform opencode\n"
        "\n"
        "import { spawn } from 'node:child_process';\n"
        "import type { Plugin } from '@opencode-ai/plugin';\n"
        "\n"
        f"const HOOKS = {events_json} as const;\n"
        "\n"
        "type HookPayload = Record<string, unknown>;\n"
        "\n"
        "function runPython(script: string, payload: HookPayload,"
        " isBlock: boolean): Promise<number> {\n"
        "  return new Promise((resolve) => {\n"
        "    const child = spawn(\n"
        "      'python',\n"
        "      ['-m', `cataforge.hook.scripts.${script}`],\n"
        "      { stdio: ['pipe', 'inherit', 'inherit'] },\n"
        "    );\n"
        "    child.on('error', () => resolve(0));\n"
        "    child.on('exit', (code) => resolve(code ?? 0));\n"
        "    child.stdin.write(JSON.stringify(payload));\n"
        "    child.stdin.end();\n"
        "  });\n"
        "}\n"
        "\n"
        "async function dispatch(event: keyof typeof HOOKS, payload: HookPayload) {\n"
        "  const handlers = HOOKS[event] ?? [];\n"
        "  for (const h of handlers) {\n"
        "    const code = await runPython(h.script, payload, h.type === 'block');\n"
        "    if (h.type === 'block' && code === 2) {\n"
        "      // Propagate block intent — OpenCode plugins throw to refuse.\n"
        "      throw new Error(`cataforge:${h.script} blocked tool execution`);\n"
        "    }\n"
        "  }\n"
        "}\n"
        "\n"
        "export const plugin: Plugin = async ({ app, client, $, event }) => {\n"
        "  for (const evt of Object.keys(HOOKS) as (keyof typeof HOOKS)[]) {\n"
        "    event.on(evt as never, (ctx: HookPayload) => dispatch(evt, ctx));\n"
        "  }\n"
        "};\n"
    )
