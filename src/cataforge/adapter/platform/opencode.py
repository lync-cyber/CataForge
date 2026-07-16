"""OpenCode platform adapter."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from cataforge.adapter.platform.adapter import PlatformAdapter
from cataforge.adapter.platform.hooks_config import merge_json_key
from cataforge.adapter.platform.mcp_config import merge_opencode_project_mcp
from cataforge.utils.atomic_write import atomic_write_text
from cataforge.utils.interpreter import interpreter_path

if TYPE_CHECKING:
    from cataforge.runtime.deploy.manifest import DeployManifest as DeployManifest


class OpenCodeAdapter(PlatformAdapter):
    @property
    def platform_id(self) -> str:
        return "opencode"

    @property
    def display_name(self) -> str:
        return "OpenCode"

    def get_project_root_env_var(self) -> str | None:
        return None

    def get_agent_scan_dirs(self) -> list[str]:
        return list(self._profile.agent_definition.scan_dirs) or [".claude/agents"]

    def get_agent_format(self) -> str:
        return "yaml-frontmatter"

    @property
    def agent_layout(self) -> str:
        return "flat"

    def agent_target_rel(self) -> str | None:
        # OpenCode doesn't surface its agents path through ``scan_dirs`` (those
        # are read-scan dirs, not the write target).
        return ".opencode/agents"

    def post_instruction_deploy(
        self,
        project_root: Path,
        *,
        dry_run: bool = False,
        manifest: DeployManifest | None = None,
    ) -> list[str]:
        # The instructions list is declared in profile.context_injection so it
        # stays auditable alongside the rest of the platform surface.  Fall
        # back to the legacy literal if the profile omits the section so older
        # scaffolds keep working without touching this code.
        ci = self.context_injection
        rd = ci.get("rules_distribution", {}) or {}
        instructions = list(rd.get("files") or ["AGENTS.md", ".cataforge/rules/*.md"])
        actions = merge_json_key(
            project_root / "opencode.json",
            "instructions",
            instructions,
            dry_run=dry_run,
        )
        if manifest is not None and not dry_run:
            manifest.record("opencode.json")
        return actions

    def write_mcp_config(
        self,
        server_id: str,
        server_config: dict[str, Any],
        project_root: Path,
        *,
        dry_run: bool = False,
    ) -> list[str]:
        return merge_opencode_project_mcp(project_root, server_id, server_config, dry_run=dry_run)

    def wrap_rule_for_platform(self, name: str, content: str) -> tuple[str, str] | None:
        """OpenCode registers rule paths via opencode.json#instructions.

        Override rules are referenced **in place** under
        ``.cataforge/platforms/opencode/overrides/rules/*.md`` (declared in
        profile.yaml#rules_distribution.files); no per-file write to a
        platform-native directory is needed. Returning ``None`` suppresses the
        base default which would otherwise write to ``opencode.json/<name>.md``
        — opencode.json is a config file, not a directory.
        """
        del name, content  # signal intentional unused
        return None

    # ---- hooks (OpenCode plugin-based surface) -----------------------

    def emit_plugin_hooks(
        self,
        project_root: Path,
        *,
        dry_run: bool = False,
        hooks_spec: dict[str, Any] | None = None,
    ) -> list[str]:
        """Generate a TypeScript plugin that bridges OpenCode events to the
        CataForge Python hook scripts.

        OpenCode doesn't accept JSON hook configs — it loads ``.ts`` plugins
        that subscribe to events like ``tool.execute.before``.  The generated
        plugin ``spawn``s each canonical hook's Python script with the event
        payload on stdin, exactly matching how Claude Code / Cursor invoke the
        same scripts.  The hook spec is supplied by the caller (the hook
        bridge) so this adapter does not reach back up into the runtime layer.
        """
        if hooks_spec is None:
            return ["opencode plugin: no hooks spec supplied — skipping"]
        spec = hooks_spec

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
        atomic_write_text(plugin_path, content)
        return [f"opencode plugin → {plugin_path.relative_to(project_root)}"]


def _render_opencode_plugin(active_events: dict[str, list[dict[str, Any]]]) -> str:
    """Render the TS plugin source.  Kept free-standing for testability."""
    import json as _json

    # Build an event → list[{script, matcher_capability, matcher_agent_id}]
    # descriptor the TS side can iterate.  All business logic lives in Python;
    # the TS plugin is a thin dispatcher that pre-filters on matcher_agent_id
    # before spawning so a non-matching agent never pays the python startup.
    descriptor: dict[str, list[dict[str, Any]]] = {}
    for plugin_event, entries in active_events.items():
        descriptor[plugin_event] = []
        for entry in entries:
            script = str(entry.get("script", "")).replace(".py", "")
            if not script:
                continue
            descriptor[plugin_event].append(
                {
                    "script": script,
                    "matcher_capability": str(entry.get("matcher_capability", "")),
                    "type": str(entry.get("type", "observe")),
                    "matcher_agent_id": [str(a) for a in (entry.get("matcher_agent_id") or [])],
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
        "  // Fail-closed: a block hook that cannot run cleanly must refuse,\n"
        "  // never allow. Spawn failure / null exit resolves to the block\n"
        "  // sentinel (2) for block hooks so a missing python/cataforge can\n"
        "  // not silently bypass guard_dangerous.\n"
        "  const failCode = isBlock ? 2 : 0;\n"
        "  return new Promise((resolve) => {\n"
        "    const child = spawn(\n"
        "      // Interpreter pinned at deploy time (sys.executable of the\n"
        "      // deploying process) — the one Python guaranteed to import\n"
        "      // cataforge; a bare 'python' lookup may not.\n"
        f"      {_json.dumps(interpreter_path())},\n"
        "      ['-m', `cataforge.runtime.hook.scripts.${script}`],\n"
        "      {\n"
        "        stdio: ['pipe', 'inherit', 'inherit'],\n"
        "        // Explicit platform identity: OpenCode exposes no IDE env\n"
        "        // var the hook runtime could sniff.\n"
        "        env: { ...process.env, CATAFORGE_PLATFORM: 'opencode' },\n"
        "      },\n"
        "    );\n"
        "    child.on('error', () => resolve(failCode));\n"
        "    child.on('exit', (code) => resolve(code ?? failCode));\n"
        "    child.stdin.write(JSON.stringify(payload));\n"
        "    child.stdin.end();\n"
        "  });\n"
        "}\n"
        "\n"
        "function agentMatches(ids: readonly string[], payload: HookPayload): boolean {\n"
        "  // Mirror Python matches_script_filters: an empty allowlist always\n"
        "  // matches; otherwise the dispatched agent (subagent_type / agent)\n"
        "  // must be on the list, else skip spawning entirely.\n"
        "  if (ids.length === 0) return true;\n"
        "  const ti = (payload.tool_input ?? {}) as Record<string, unknown>;\n"
        "  const candidate = (ti.subagent_type ?? ti.agent ?? payload.agent ?? '') as string;\n"
        "  return candidate !== '' && ids.includes(candidate);\n"
        "}\n"
        "\n"
        "async function dispatch(event: keyof typeof HOOKS, payload: HookPayload) {\n"
        "  const handlers = HOOKS[event] ?? [];\n"
        "  for (const h of handlers) {\n"
        "    if (!agentMatches(h.matcher_agent_id, payload)) continue;\n"
        "    const code = await runPython(h.script, payload, h.type === 'block');\n"
        "    if (h.type === 'block' && code !== 0) {\n"
        "      // Only a clean exit 0 allows; any non-zero (explicit block 2,\n"
        "      // crash, or fail-closed sentinel) refuses. OpenCode plugins\n"
        "      // throw to block tool execution.\n"
        "      throw new Error(`cataforge:${h.script} blocked tool execution`);\n"
        "    }\n"
        "  }\n"
        "}\n"
        "\n"
        "export const plugin: Plugin = async ({ app, client, $, event }) => {\n"
        "  for (const evt of Object.keys(HOOKS) as (keyof typeof HOOKS)[]) {\n"
        "    event.on(evt as never, async (ctx: HookPayload) => { await dispatch(evt, ctx); });\n"
        "  }\n"
        "};\n"
    )
