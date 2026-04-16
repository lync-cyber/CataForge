"""Hook bridge — generate platform hook configs from hooks.yaml + adapter.

Bridges CataForge's canonical hook spec (``hooks.yaml``) to each platform's
native hook config, collecting *warnings* for any hook entry that could not
be materialised natively (missing event mapping, missing matcher mapping,
unimplemented degradation strategy).  Callers (``deploy`` / ``doctor``) are
expected to surface those warnings to the user so silent functional loss
becomes observable.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, NamedTuple

import yaml

from cataforge.core.paths import find_project_root
from cataforge.platform.base import PlatformAdapter

logger = logging.getLogger(__name__)


# Highest schema version this release understands.  Older hooks.yaml files
# are treated as v1 (missing/optional fields default to "no filter").
SUPPORTED_SCHEMA_VERSION = 2


class HookGenerationResult(NamedTuple):
    """Return value of :func:`generate_platform_hooks`.

    Using a NamedTuple keeps old positional-unpacking call sites working while
    attaching a second, named field for warnings.
    """

    hooks: dict[str, Any]
    warnings: list[str]


def load_hooks_spec(hooks_yaml: Path | None = None) -> dict[str, Any]:
    """Load the canonical hook specification from hooks.yaml."""
    if hooks_yaml is None:
        hooks_yaml = find_project_root() / ".cataforge" / "hooks" / "hooks.yaml"

    with open(hooks_yaml, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"hooks.yaml must be a mapping, got {type(data).__name__}")
    return data


def check_schema_version(spec: dict[str, Any]) -> str | None:
    """Validate ``schema_version`` against this release.

    Returns ``None`` when the version is supported (including the implicit
    v1 for files authored before the field existed), otherwise a warning
    string ready to show the user.
    """
    raw = spec.get("schema_version", 1)
    try:
        version = int(raw)
    except (TypeError, ValueError):
        return (
            f"hooks.yaml: schema_version must be an integer, got {raw!r}. "
            "Treating as v1."
        )
    if version > SUPPORTED_SCHEMA_VERSION:
        return (
            f"hooks.yaml: schema_version={version} is newer than this "
            f"cataforge release understands (max v{SUPPORTED_SCHEMA_VERSION}). "
            "Consider upgrading the package."
        )
    return None


def generate_platform_hooks(adapter: PlatformAdapter) -> HookGenerationResult:
    """Generate platform-native hook configuration.

    Returns ``(hooks, warnings)``.  ``hooks`` is suitable for writing into
    the platform's hook config file; ``warnings`` enumerates every canonical
    hook that could not be emitted natively so the caller can surface it.
    """
    spec = load_hooks_spec()
    warnings: list[str] = []

    version_warning = check_schema_version(spec)
    if version_warning:
        warnings.append(version_warning)

    event_map = adapter.hook_event_map
    degradation = adapter.hook_degradation
    tool_map = adapter.get_tool_map()
    hook_tool_overrides = getattr(adapter, "hook_tool_overrides", {}) or {}
    command_template = adapter.get_hook_command_template()

    platform_hooks: dict[str, list[dict[str, Any]]] = {}

    for event_name, hook_list in spec.get("hooks", {}).items():
        platform_event = event_map.get(event_name)
        if platform_event is None:
            for hook_entry in hook_list:
                script_name = _script_to_hook_name(hook_entry.get("script", "?"))
                warnings.append(
                    f"{adapter.platform_id}: event {event_name!r} has no platform "
                    f"mapping — hook {script_name!r} will not fire."
                )
            continue

        translated: list[dict[str, Any]] = []
        for hook_entry in hook_list:
            capability = hook_entry.get("matcher_capability", "")
            hook_name = _script_to_hook_name(hook_entry.get("script", ""))

            status = degradation.get(hook_name, "native")
            if status != "native":
                # Degraded/skipped hooks are handled by apply_degradation; we
                # still surface the loss of the native code path here so the
                # user understands that runtime blocking/observing is gone.
                warnings.append(
                    f"{adapter.platform_id}: hook {hook_name!r} is {status!r} "
                    f"(not native) — runtime behaviour replaced by a degradation "
                    "strategy (see `hook list`)."
                )
                continue

            if capability:
                native_tool = hook_tool_overrides.get(capability) or tool_map.get(
                    capability
                )
                if native_tool is None:
                    warnings.append(
                        f"{adapter.platform_id}: matcher_capability "
                        f"{capability!r} has no tool mapping — hook "
                        f"{hook_name!r} on event {event_name} skipped."
                    )
                    continue
                platform_matcher = native_tool
            else:
                platform_matcher = ""

            module_name = _script_to_hook_name(hook_entry.get("script", ""))
            command = _resolve_command(command_template, module_name)

            # Emit the platform-native hook entry type (typically "command" for
            # JSON-config platforms like Claude Code / Cursor / Codex). The
            # internal "block" / "observe" in hooks.yaml is a CataForge-side
            # semantic tag used for CLI display and future policy — it must
            # not leak into platform configs, where it would be rejected or
            # silently ignored by the host IDE.
            platform_entry_type = adapter.hook_entry_type or hook_entry.get(
                "type", "command"
            )

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

    return HookGenerationResult(platform_hooks, warnings)


def _resolve_command(template: str, script_name: str) -> str:
    """Resolve a hook command line.

    Built-in scripts live in ``cataforge.hook.scripts.<name>`` and use the
    adapter's ``{module}`` template.  User-authored scripts are referenced
    with a ``custom:`` prefix (``script: custom:my_hook``) and are invoked
    directly from ``.cataforge/hooks/custom/<name>.py`` — this lets a project
    ship its own hooks without needing a plugin mechanism.
    """
    if script_name.startswith("custom:"):
        custom_name = script_name.removeprefix("custom:")
        # Path is relative to the project root, which every supported IDE
        # uses as the hook process's cwd.
        return f"python .cataforge/hooks/custom/{custom_name}.py"
    return template.format(module=script_name)


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

    # Platforms with a plugin-based hook surface (OpenCode) materialise
    # their hooks through a generated plugin file in addition to whatever
    # per-hook degradation strategies still apply for events the plugin
    # host cannot represent (e.g. Notification on OpenCode).
    plugin_actions = _emit_plugin_hooks(adapter, project_root, dry_run=dry_run)
    if plugin_actions is not None:
        actions.extend(plugin_actions)

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


def _emit_plugin_hooks(
    adapter: PlatformAdapter, project_root: Path, *, dry_run: bool = False
) -> list[str] | None:
    """Call the adapter's ``emit_plugin_hooks`` hook if defined.

    Platforms that use plugin files instead of JSON hook configs (OpenCode)
    implement this method to generate the plugin wrapper in one go.  Returns
    ``None`` when the adapter has no plugin surface — in that case the
    caller falls back to per-hook rules injection / skip.
    """
    fn = getattr(adapter, "emit_plugin_hooks", None)
    if fn is None:
        return None
    return list(fn(project_root, dry_run=dry_run))


def _script_to_hook_name(script: str) -> str:
    return script.replace(".py", "")
