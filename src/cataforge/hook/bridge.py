"""Hook bridge — generate platform hook configs from hooks.yaml + adapter.

Fixes C-2: hook command template now comes from the platform adapter,
eliminating the hardcoded $CLAUDE_PROJECT_DIR.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from cataforge.core.paths import find_project_root
from cataforge.platform.base import PlatformAdapter

logger = logging.getLogger(__name__)


def load_hooks_spec(hooks_yaml: Path | None = None) -> dict[str, Any]:
    """Load the canonical hook specification from hooks.yaml."""
    if hooks_yaml is None:
        hooks_yaml = find_project_root() / ".cataforge" / "hooks" / "hooks.yaml"

    with open(hooks_yaml, encoding="utf-8") as f:
        return dict(yaml.safe_load(f))


def generate_platform_hooks(adapter: PlatformAdapter) -> dict[str, Any]:
    """Generate platform-native hook configuration.

    Returns a dict suitable for writing into the platform's hook config file.
    """
    spec = load_hooks_spec()
    event_map = adapter.hook_event_map
    degradation = adapter.hook_degradation
    tool_map = adapter.get_tool_map()
    hook_tool_overrides = getattr(adapter, "hook_tool_overrides", {}) or {}
    command_template = adapter.get_hook_command_template()

    platform_hooks: dict[str, list[dict[str, Any]]] = {}

    for event_name, hook_list in spec.get("hooks", {}).items():
        platform_event = event_map.get(event_name)
        if platform_event is None:
            logger.debug(
                "hook skip: canonical event %r has no platform mapping (platform=%s)",
                event_name,
                adapter.platform_id,
            )
            continue

        translated: list[dict[str, Any]] = []
        for hook_entry in hook_list:
            capability = hook_entry.get("matcher_capability", "")
            hook_name = _script_to_hook_name(hook_entry.get("script", ""))

            if degradation.get(hook_name) != "native":
                logger.debug(
                    "hook skip: %s / %s — degradation[%r]=%r (need 'native')",
                    event_name,
                    hook_name,
                    hook_name,
                    degradation.get(hook_name),
                )
                continue

            if capability:
                native_tool = hook_tool_overrides.get(capability) or tool_map.get(capability)
                if native_tool is None:
                    logger.debug(
                        "hook skip: %s / %s — matcher_capability %r has no tool mapping",
                        event_name,
                        hook_name,
                        capability,
                    )
                    continue
                platform_matcher = native_tool
            else:
                platform_matcher = ""

            module_name = _script_to_hook_name(hook_entry.get("script", ""))
            command = command_template.format(module=module_name)

            # Emit the platform-native hook entry type (typically "command" for
            # JSON-config platforms like Claude Code / Cursor / Codex). The
            # internal "block" / "observe" in hooks.yaml is a CataForge-side
            # semantic tag used for CLI display and future policy — it must
            # not leak into platform configs, where it would be rejected or
            # silently ignored by the host IDE.
            platform_entry_type = adapter.hook_entry_type or hook_entry.get("type", "command")

            translated.append(
                {
                    "matcher": platform_matcher,
                    "hooks": [
                        {
                            "type": platform_entry_type,
                            "command": command,
                        }
                    ],
                }
            )

        if translated:
            platform_hooks[platform_event] = translated

    return platform_hooks


def get_degraded_hooks(adapter: PlatformAdapter) -> list[dict[str, Any]]:
    """Get hooks that need degradation and their fallback strategies."""
    spec = load_hooks_spec()
    degradation = adapter.hook_degradation
    templates = spec.get("degradation_templates", {})

    result: list[dict[str, Any]] = []
    for hook_name, status in degradation.items():
        if status == "degraded" and hook_name in templates:
            template = templates[hook_name]
            result.append(
                {
                    "name": hook_name,
                    "strategy": template.get("strategy", "skip"),
                    "content": template.get("content", ""),
                    "reason": template.get("reason", ""),
                }
            )
    return result


def apply_degradation(
    adapter: PlatformAdapter, project_root: Path, *, dry_run: bool = False
) -> list[str]:
    """Materialize degradation strategies into file changes."""
    degraded = get_degraded_hooks(adapter)
    actions: list[str] = []
    rules_content_parts: list[str] = []

    for entry in degraded:
        strategy = entry["strategy"]
        content = entry["content"]

        if strategy == "rules_injection":
            rules_content_parts.append(content)
        elif strategy == "skip":
            actions.append(f"SKIP: {entry['name']} — {entry.get('reason', '')}")

    if rules_content_parts:
        auto_rules_dir = (
            project_root
            / ".cataforge"
            / "platforms"
            / adapter.platform_id
            / "overrides"
            / "rules"
        )
        auto_rules_path = auto_rules_dir / "auto-safety-degradation.md"
        if dry_run:
            actions.append(
                f"would write rules_injection → {auto_rules_path} "
                f"({len(rules_content_parts)} fragment(s))"
            )
        else:
            auto_rules_dir.mkdir(parents=True, exist_ok=True)
            auto_rules_path.write_text(
                "# Auto-generated Safety Rules (Hook Degradation)\n\n"
                + "\n\n".join(rules_content_parts),
                encoding="utf-8",
            )
            actions.append(f"rules_injection → {auto_rules_path}")

    return actions


def _script_to_hook_name(script: str) -> str:
    return script.replace(".py", "")
